"""Contract tests for the HTTP API described in 03-design.md.

End to end against `reader.app.create_app` with a `FakeSynthesizer` injected,
so no model download or wall-clock audio cost is needed:
client.post("/api/documents", files=...) -> {"id", "page_count", "pages": [...]}.

Assumption: create_app() takes the synthesizer as keyword arg `synthesizer` --
03-design.md doesn't name it; if it turns out different, these fixtures are
the only place to change.
"""

from __future__ import annotations

import math

import pymupdf
import pytest
from fastapi.testclient import TestClient
from reader.app import create_app
from reader.services.extraction import render
from reader.services.speech import FakeSynthesizer

_NARRATION_TEXT = "One two three. Four five six."


def _blank_pdf() -> bytes:
    """A single page with no text layer at all -- what a scanned PDF looks like.

    >>> pymupdf.open(stream=_blank_pdf(), filetype="pdf")[0].get_text("words")
    []
    """
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()


def _pdf_with_blank_cover_page(text: str) -> bytes:
    """A two-page PDF: a blank cover page, then a page with `text` -- the shape
    of a real document with a blank title/cover page, which must NOT be
    mistaken for "no readable text".

    >>> pages = pymupdf.open(stream=_pdf_with_blank_cover_page("Hi"), filetype="pdf")
    >>> len(pages)
    2
    >>> pages[0].get_text("words")
    []
    """
    doc = pymupdf.open()
    doc.new_page()
    doc.insert_pdf(pymupdf.open(stream=render(text), filetype="pdf"))
    return doc.tobytes()


def _encrypted_pdf() -> bytes:
    """A password-protected PDF -- pymupdf can write the encryption straight into
    the bytes it returns, no temp file needed.

    >>> pymupdf.open(stream=_encrypted_pdf(), filetype="pdf").is_encrypted
    True
    """
    doc = pymupdf.open(stream=render("Secret quarterly results."), filetype="pdf")
    return doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="hunter2"
    )


class _FailsOnce:
    """A synthesiser that fails the second sentence once, then works.

    >>> s = _FailsOnce()
    >>> s.synthesize("a", voice="am_adam") is not None
    True
    """

    def __init__(self) -> None:
        self._calls = 0
        self._fake = FakeSynthesizer()

    def synthesize(self, text: str, *, voice: str) -> bytes:
        self._calls += 1
        if self._calls == 2:
            raise RuntimeError("Kokoro exploded mid-page")
        return self._fake.synthesize(text, voice=voice)


@pytest.fixture
def client():
    app = create_app(synthesizer=FakeSynthesizer())
    return TestClient(app)


@pytest.fixture
def uploaded_document(client):
    pdf_bytes = render(_NARRATION_TEXT)
    response = client.post(
        "/api/documents",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )
    return response.json()


def test_uploading_a_pdf_returns_the_documented_shape(client):
    pdf_bytes = render(_NARRATION_TEXT)

    response = client.post(
        "/api/documents",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "id" in body
    assert body["page_count"] == len(body["pages"])
    assert body["page_count"] >= 1

    first_page = body["pages"][0]
    assert first_page["index"] == 0
    assert first_page["width"] > 0
    assert first_page["height"] > 0
    assert len(first_page["words"]) > 0
    for word in first_page["words"]:
        assert isinstance(word["text"], str) and word["text"]
        assert word["x1"] > word["x0"]
        assert word["y1"] > word["y0"]


def test_uploading_a_non_pdf_file_is_rejected(client):
    response = client.post(
        "/api/documents",
        files={"file": ("notes.txt", b"this is not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert "PDF" in response.text


def test_uploading_an_encrypted_pdf_says_password_protected_not_invalid(client):
    response = client.post(
        "/api/documents",
        files={"file": ("locked.pdf", _encrypted_pdf(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "password-protected" in response.text
    assert "not a valid PDF" not in response.text


def test_uploading_corrupt_bytes_named_pdf_reports_the_problem_once(client):
    response = client.post(
        "/api/documents",
        files={"file": ("broken.pdf", b"this is garbage, not a pdf at all", "application/pdf")},
    )

    assert response.status_code == 400
    # The bug was the phrase doubling itself ("not a valid PDF: not a valid
    # PDF") because the route re-wrapped an already-worded exception. Asserting
    # the exact string (rather than merely "at most once") pins the wording the
    # reader is meant to see, which "at most once" would let drift silently.
    assert response.json()["detail"] == "That file is not a readable PDF"


def test_uploading_a_pdf_with_no_readable_text_is_rejected(client):
    response = client.post(
        "/api/documents",
        files={"file": ("scan.pdf", _blank_pdf(), "application/pdf")},
    )

    assert response.status_code == 400
    assert "no readable text" in response.text


def test_a_blank_cover_page_does_not_count_as_no_readable_text(client):
    pdf_bytes = _pdf_with_blank_cover_page(_NARRATION_TEXT)

    response = client.post(
        "/api/documents",
        files={"file": ("cover.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["page_count"] == 2


def test_narration_spans_cover_the_page_word_by_word(client, uploaded_document):
    doc_id = uploaded_document["id"]
    word_count = len(uploaded_document["pages"][0]["words"])

    response = client.get(
        f"/api/documents/{doc_id}/pages/0/narration", params={"voice": "am_adam"}
    )

    assert response.status_code == 200
    body = response.json()
    spans = body["spans"]

    assert len(spans) == word_count
    starts = [span["start"] for span in spans]
    assert starts == sorted(starts)
    for earlier, later in zip(spans, spans[1:], strict=False):
        assert earlier["end"] <= later["start"] + 1e-6
    assert math.isclose(spans[-1]["end"], body["duration"], abs_tol=1e-6)


def test_health_check_returns_200(client):
    response = client.get("/api/health")

    assert response.status_code == 200


def _audio_url(doc_id: str, page_index: int = 0) -> str:
    return f"/api/documents/{doc_id}/pages/{page_index}/audio.wav"


def test_audio_route_advertises_byte_range_support(client, uploaded_document):
    response = client.get(_audio_url(uploaded_document["id"]))

    assert response.headers.get("accept-ranges") == "bytes"


def test_a_byte_range_request_returns_a_206_partial_response(client, uploaded_document):
    response = client.get(_audio_url(uploaded_document["id"]), headers={"Range": "bytes=0-1023"})

    assert response.status_code == 206
    assert len(response.content) == 1024
    content_range = response.headers["content-range"]
    assert content_range.startswith("bytes 0-1023/")
    assert int(content_range.split("/")[-1]) > 1024


def test_a_tail_byte_range_request_returns_the_end_of_the_audio(client, uploaded_document):
    url = _audio_url(uploaded_document["id"])
    full_body = client.get(url).content
    total = len(full_body)

    response = client.get(url, headers={"Range": f"bytes={total - 100}-"})

    assert response.status_code == 206
    assert response.content == full_body[-100:]


def test_an_unsatisfiable_byte_range_returns_416(client, uploaded_document):
    url = _audio_url(uploaded_document["id"])
    total = len(client.get(url).content)

    response = client.get(url, headers={"Range": f"bytes={total + 1000}-"})

    assert response.status_code == 416


def test_head_on_the_audio_route_reports_headers_with_no_body(client, uploaded_document):
    url = _audio_url(uploaded_document["id"])
    get_response = client.get(url)

    response = client.head(url)

    assert response.status_code == 200
    assert response.headers["content-type"] == get_response.headers["content-type"]
    assert response.headers["content-length"] == get_response.headers["content-length"]
    assert response.content == b""


def test_a_synthesis_failure_is_not_cached_so_the_next_request_recovers():
    app = create_app(synthesizer=_FailsOnce())
    api = TestClient(app, raise_server_exceptions=False)
    upload = api.post(
        "/api/documents",
        files={"file": ("sample.pdf", render(_NARRATION_TEXT), "application/pdf")},
    ).json()
    doc_id, word_count = upload["id"], len(upload["pages"][0]["words"])
    url = f"/api/documents/{doc_id}/pages/0/narration"

    failed = api.get(url, params={"voice": "am_adam"})
    assert failed.status_code == 500

    recovered = api.get(url, params={"voice": "am_adam"})
    assert recovered.status_code == 200
    spans = recovered.json()["spans"]
    assert len(spans) == word_count
    assert [span["word_index"] for span in spans] == list(range(word_count))
