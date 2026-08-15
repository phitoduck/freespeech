"""FastAPI app wiring: routes call domain/services, no business logic lives here.

Flow:
    POST /api/documents        -> extract() -> Document, kept in an in-memory Store
    GET  .../narration          -> split_sentences() -> synthesize each sentence on a
                                    worker thread -> wav_duration() -> build_timeline()
                                    -> concat_wavs(), cached by (doc_id, page, voice)
    GET  .../audio.wav           -> same cache, raw WAV bytes, Range-seekable
    GET  /api/health             -> liveness + which synthesizer is wired up
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

import anyio.to_thread
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from reader.domain.documents import Document
from reader.domain.sentences import split_sentences
from reader.domain.timeline import build_timeline, total_duration
from reader.services.extraction import EncryptedPDF, extract
from reader.services.speech import (
    KokoroSynthesizer,
    SpeechSynthesizer,
    concat_wavs,
    wav_duration,
)

DEFAULT_VOICE = "am_adam"


@dataclass(slots=True)
class Narration:
    """One page's synthesised audio and its word-highlight timeline."""

    wav: bytes
    duration: float
    spans: list[dict[str, float | int]]


@dataclass(slots=True)
class Store:
    """In-process state only; persistence is explicitly deferred (ADR 0005)."""

    documents: dict[str, Document] = field(default_factory=dict)
    narration_cache: dict[tuple[str, int, str], Narration] = field(default_factory=dict)


def _document_json(doc: Document) -> dict:
    """Serialize a Document to the shape `POST /api/documents` returns.

    >>> from reader.services.extraction import extract, render
    >>> body = _document_json(extract(render("Hi")))
    >>> body["page_count"], body["pages"][0]["words"][0]["text"]
    (1, 'Hi')
    """
    return {
        "id": doc.id,
        "page_count": doc.page_count,
        "pages": [
            {
                "index": page.index,
                "width": page.width,
                "height": page.height,
                "words": [
                    {
                        "text": word.text,
                        "x0": word.box.x0,
                        "y0": word.box.y0,
                        "x1": word.box.x1,
                        "y1": word.box.y1,
                    }
                    for word in page.words
                ],
            }
            for page in doc.pages
        ],
    }


def _partial_content(body: bytes, range_header: str | None) -> tuple[int, dict[str, str], bytes]:
    """Slice `body` per an HTTP `Range: bytes=start-end` header, for seekable audio.

    Returns `(status, extra_headers, payload)`: 200 with the whole body if
    there is no range, 206 with a `Content-Range` header and the requested
    slice (an open end means "to the last byte"), or 416 if the range starts
    at or beyond the end of the body.

    >>> _partial_content(b"0123456789", "bytes=2-4")
    (206, {'Content-Range': 'bytes 2-4/10'}, b'234')
    >>> _partial_content(b"0123456789", "bytes=8-")
    (206, {'Content-Range': 'bytes 8-9/10'}, b'89')
    >>> _partial_content(b"0123456789", "bytes=20-")
    (416, {'Content-Range': 'bytes */10'}, b'')
    """
    total = len(body)
    if not range_header or not range_header.startswith("bytes="):
        return 200, {}, body

    start_str, _, end_str = range_header.removeprefix("bytes=").partition("-")
    start = int(start_str) if start_str else 0
    end = min(int(end_str), total - 1) if end_str else total - 1

    if start >= total or start > end:
        return 416, {"Content-Range": f"bytes */{total}"}, b""
    return 206, {"Content-Range": f"bytes {start}-{end}/{total}"}, body[start : end + 1]


async def _narrate(
    store: Store, synthesizer: SpeechSynthesizer, doc: Document, page_index: int, voice: str
) -> Narration:
    """Synthesize a page's narration sentence by sentence, cached by (doc, page, voice).

    # -> await _narrate(store, FakeSynthesizer(), doc, 0, "am_adam")
    # -> Narration(wav=b"RIFF...", duration=0.4,
    #              spans=[{"word_index": 0, "start": 0.0, "end": 0.4}])
    """
    key = (doc.id, page_index, voice)
    cached = store.narration_cache.get(key)
    if cached is not None:
        return cached

    page = doc.page(page_index)
    words = tuple(word.text for word in page.words)
    sentences = split_sentences(words)

    wavs = []
    for sentence in sentences:
        synthesize = functools.partial(synthesizer.synthesize, sentence.text, voice=voice)
        wavs.append(await anyio.to_thread.run_sync(synthesize))

    durations = [wav_duration(wav) for wav in wavs]
    spans = build_timeline(sentences, durations)

    narration = Narration(
        wav=concat_wavs(wavs),
        duration=total_duration(spans),
        spans=[{"word_index": s.word_index, "start": s.start, "end": s.end} for s in spans],
    )
    store.narration_cache[key] = narration
    return narration


def create_app(*, synthesizer: SpeechSynthesizer | None = None) -> FastAPI:
    """Build the API. `synthesizer` is constructed here, not as a default argument
    value, so importing this module never loads the Kokoro model.

    >>> from reader.services.speech import FakeSynthesizer
    >>> create_app(synthesizer=FakeSynthesizer()).state.synthesizer.__class__.__name__
    'FakeSynthesizer'
    """
    app = FastAPI(title="pdf-karaoke-reader")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = Store()
    app.state.synthesizer = synthesizer if synthesizer is not None else KokoroSynthesizer()

    @app.get("/api/health")
    def health() -> dict:
        """Liveness probe reporting the default voice and which synthesizer is wired up.

        # -> {"status": "ok", "voice": "am_adam", "synthesizer": "FakeSynthesizer"}
        """
        return {
            "status": "ok",
            "voice": DEFAULT_VOICE,
            "synthesizer": type(app.state.synthesizer).__name__,
        }

    @app.post("/api/documents")
    async def upload_document(file: UploadFile) -> dict:
        """Extract an uploaded PDF into pages of words and keep it in memory.

        # -> POST a one-page PDF -> {"id": "ab12cd34ef56", "page_count": 1, "pages": [...]}
        # -> POST a locked PDF   -> 400 "That PDF is password-protected"
        # -> POST anything else  -> 400 "That file is not a readable PDF"
        """
        pdf_bytes = await file.read()
        try:
            doc = extract(pdf_bytes, filename=file.filename or "document.pdf")
        except EncryptedPDF as exc:
            raise HTTPException(400, "That PDF is password-protected") from exc
        except ValueError as exc:
            raise HTTPException(400, "That file is not a readable PDF") from exc
        if not any(page.words for page in doc.pages):
            raise HTTPException(400, "That PDF has no readable text — it may be a scan")
        app.state.store.documents[doc.id] = doc
        return _document_json(doc)

    async def resolve(doc_id: str, page: int, voice: str) -> Narration:
        """Find the document and page (404 if absent), then narrate or reuse the cache.

        # -> await resolve("ab12cd34ef56", 0, "am_adam") -> Narration(...)
        # -> await resolve("nope", 0, "am_adam")         -> raises HTTPException(404)
        """
        store: Store = app.state.store
        try:
            doc = store.documents[doc_id]
            doc.page(page)  # 404 before doing any synthesis work
        except KeyError:
            raise HTTPException(404, f"no document with id {doc_id!r}") from None
        except IndexError:
            raise HTTPException(404, f"page {page} out of range for {doc_id!r}") from None
        return await _narrate(store, app.state.synthesizer, doc, page, voice)

    @app.get("/api/documents/{doc_id}/pages/{page}/narration")
    async def get_narration(doc_id: str, page: int, voice: str = DEFAULT_VOICE) -> dict:
        """Word-timing spans plus an audio URL for one page's narration in one voice.

        # -> GET .../pages/0/narration?voice=am_adam
        # -> {"audio_url": ".../audio.wav?voice=am_adam", "duration": 8.69, "spans": [...]}
        """
        narration = await resolve(doc_id, page, voice)
        return {
            "audio_url": f"/api/documents/{doc_id}/pages/{page}/audio.wav?voice={voice}",
            "duration": narration.duration,
            "spans": narration.spans,
        }

    @app.api_route("/api/documents/{doc_id}/pages/{page}/audio.wav", methods=["GET", "HEAD"])
    async def get_audio(
        request: Request, doc_id: str, page: int, voice: str = DEFAULT_VOICE
    ) -> Response:
        """The page's WAV audio, Range-seekable so the browser can seek at all.

        # -> GET  .../audio.wav                      -> 200, whole body
        # -> GET  .../audio.wav  Range: bytes=0-1023 -> 206, Content-Range: bytes 0-1023/510764
        # -> HEAD .../audio.wav                      -> 200, Content-Length, empty body
        """
        body = (await resolve(doc_id, page, voice)).wav

        if request.method == "HEAD":
            headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(body))}
            return Response(content=b"", media_type="audio/wav", headers=headers)

        status, extra_headers, payload = _partial_content(body, request.headers.get("range"))
        headers = {"Accept-Ranges": "bytes", **extra_headers}
        return Response(
            content=payload, status_code=status, media_type="audio/wav", headers=headers
        )

    return app
