# Change the voice

The reader narrates with `am_adam` by default. Kokoro ships twenty American
English voices, and several other languages.

## For a single request

The narration endpoint takes a `voice` query parameter:

```bash
curl "http://localhost:8000/api/documents/$DOC_ID/pages/0/narration?voice=am_michael"
```

Narration is cached per `(document, page, voice)`, so asking for a second voice
synthesises the page again rather than returning the first one.

## For the whole app

Change the `DEFAULT_VOICE` constant in `apps/api/src/reader/app.py`, or set the
voice in the frontend's narration request in `apps/web/src/App.tsx`.

## The voices

American English (`lang="en-us"`), which is what this app requests:

| Male | Female |
|---|---|
| `am_adam`, `am_echo`, `am_eric`, `am_fenrir`, `am_liam`, `am_michael`, `am_onyx`, `am_puck`, `am_santa` | `af_heart`, `af_alloy`, `af_aoede`, `af_bella`, `af_jessica`, `af_kore`, `af_nicole`, `af_nova`, `af_river`, `af_sarah`, `af_sky` |

Kokoro also has British English, Japanese, Mandarin, Spanish, French, Hindi,
Italian and Brazilian Portuguese voices. Using them means passing a matching
`lang` — `fastkokoro` validates that the voice belongs to the language and
rejects a mismatch.

!!! warning "Word timing is tuned for English"
    The speech-cost estimate behind the highlight counts vowel groups as a proxy
    for syllables, which is an English assumption. Sentence boundaries stay
    exact in any language — they are measured — but the split *within* a
    sentence will be poorer. See [How the karaoke timing
    works](../explanation/timing.md).

## Check it took effect

```bash
curl -s http://localhost:8000/api/health
```

```json
{"status": "ok", "voice": "am_adam", "synthesizer": "KokoroSynthesizer"}
```

If `synthesizer` says `FakeSynthesizer`, you are running the test double — it
returns silence. Start the API with the model extra:

```bash
make api          # uv run --extra tts uvicorn ...
```
