# HTTP API

The API runs on port 8000. The web app proxies `/api` to it, so in the browser
these are same-origin.

Every response below was captured from a running server.

---

## `GET /api/health`

Reports whether the real model is loaded or a test double is standing in.

```bash
curl -s http://localhost:8000/api/health
```

```json
{"status": "ok", "voice": "am_adam", "synthesizer": "KokoroSynthesizer"}
```

`synthesizer` is `FakeSynthesizer` when the app was built for tests — that one
returns silence, so if narration is inaudible, check here first.

---

## `POST /api/documents`

Upload a PDF. Multipart, field name `file`.

```bash
curl -F "file=@page.pdf" http://localhost:8000/api/documents
```

```json
{
  "id": "8f351009e994",
  "page_count": 1,
  "pages": [
    {
      "index": 0,
      "width": 612.0,
      "height": 792.0,
      "words": [
        {"text": "The",   "x0": 72.0,  "y0": 71.1, "x1": 92.68,  "y1": 87.59},
        {"text": "quick", "x0": 96.01, "y0": 71.1, "x1": 124.02, "y1": 87.59}
      ]
    }
  ]
}
```

Words arrive in reading order, each with the rectangle it occupies in PDF points
(origin top-left). That rectangle is what a highlight would be drawn over.

**`400`** — the upload could not be read as text. The message distinguishes why:

| Message | When |
|---|---|
| `That file is not a readable PDF` | the bytes are not a valid PDF at all |
| `That PDF is password-protected` | the PDF opens but is encrypted |
| `That PDF has no readable text — it may be a scan` | a valid, unencrypted PDF with no extractable text on any page |

---

## `GET /api/documents/{id}/pages/{n}/narration`

Synthesise the page and return the word timeline. This is the slow call: the
page is split into sentences and each is synthesised separately.

!!! important "`{n}` counts from zero"
    The first page is `pages/0`. For a two-page document `pages/0` and `pages/1`
    are valid and `pages/2` returns 404. The reader's own interface counts from
    one — it shows *Page 1 of 2* for `pages/0` — because that is what a person
    expects to read, but the API index is unchanged.

| Parameter | Default | |
|---|---|---|
| `voice` | `am_adam` | any Kokoro voice for the language — see [Change the voice](../how-to/change-the-voice.md) |

```bash
curl -s "http://localhost:8000/api/documents/8f351009e994/pages/0/narration?voice=am_adam"
```

```json
{
  "audio_url": "/api/documents/8f351009e994/pages/0/audio.wav?voice=am_adam",
  "duration": 8.693333333333333,
  "spans": [
    {"word_index": 0, "start": 0.0,       "end": 0.2657792},
    {"word_index": 1, "start": 0.2657792, "end": 0.5553152},
    {"word_index": 2, "start": 0.5553152, "end": 0.8448512}
  ]
}
```

`spans` has exactly one entry per word on the page, in order. They are
contiguous — each span's `start` is the previous span's `end`, the same float —
and the last one's `end` is `duration`. Those are guarantees, not observations;
see [How the karaoke timing works](../explanation/timing.md).

Results are cached per `(document, page, voice)`. Asking for a second voice
synthesises the page again.

**`404`** — unknown document id, or the page is out of range.

---

## `GET /api/documents/{id}/pages/{n}/audio.wav`

The narration audio: 24 kHz mono 16-bit WAV.

```bash
curl -s -D- -o /dev/null \
  -H "Range: bytes=0-1023" \
  "http://localhost:8000/api/documents/8f351009e994/pages/0/audio.wav?voice=am_adam"
```

```http
HTTP/1.1 206 Partial Content
accept-ranges: bytes
content-range: bytes 0-1023/510764
content-length: 1024
content-type: audio/wav
```

!!! important "Byte ranges are not optional"
    A browser will not let you seek a media element unless the server supports
    byte ranges — `audio.seekable` comes back as `[0, 0]` and assigning
    `currentTime` silently does nothing. Clicking a word to jump the narration
    depends entirely on this.

    This was shipped broken and caught by the end-to-end scenarios, which is the
    only level at which it *could* have been caught: the contract test asserted
    `200` and `audio/wav`, and both were true.

Supported: `bytes=0-1023`, open-ended tails (`bytes=1000-`), `416` for a range
starting past the end, and `HEAD` for `Content-Length` without a body.

---

## Storage

Documents live in a dictionary in the server process. Restarting the API loses
them. This is a deliberate deferral for a local prototype, not an oversight.
