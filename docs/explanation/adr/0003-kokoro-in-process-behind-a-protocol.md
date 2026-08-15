# 3. Run Kokoro in-process, behind a protocol

- Status: accepted
- Date: 2026-08-15

## Context

The goal named "fast-kokoro". No such package exists; the real one is
[`fastkokoro`](https://pypi.org/project/fastkokoro/), which ships two surfaces:

- an OpenAI-compatible HTTP server (`fastkokoro` → `:8880`, `POST /v1/audio/speech`)
- a direct Python API: `FastKokoro().create(text, voice=..., response_format=...)`

Measured on this machine: engine init 18.3s cold (model download + load), then
~2s to synthesise a short sentence. The 82M model is the same either way.

## Decision

Use the **in-process Python API**, cached as a module-level singleton, and put a
`SpeechSynthesizer` `Protocol` in front of it:

```python
class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, *, voice: str) -> bytes: ...
```

`KokoroSynthesizer` is the real one. `FakeSynthesizer` returns a genuine but
silent WAV whose length is a deterministic function of the text.

## Consequences

- One process to run instead of two. `make dev` starts the API and the web app,
  and that is the whole system.
- `response_format="wav"` means the duration comes from the stdlib `wave` module
  — a frame count divided by a sample rate. No ffprobe, no subprocess, no
  guessing. This is what makes the derived timeline in ADR 0002 exact at
  sentence boundaries.
- **The test suite never touches the model.** Injecting `FakeSynthesizer` keeps
  the BDD and contract suites fast, offline, and deterministic; a single test
  marked `@pytest.mark.kokoro` exercises the real thing, and the running app
  always uses it.
- Synthesis is CPU-bound and would block the event loop, so the route offloads it
  with `anyio.to_thread.run_sync`.
- The cold start is paid **lazily, by whichever request needs speech first** —
  `KokoroSynthesizer` imports `fastkokoro` and builds the engine inside
  `synthesize()`, so importing the module (and starting the server) loads
  nothing.

    !!! warning "Corrected 2026-08-15"
        This originally claimed the cost was "paid once, in a FastAPI lifespan
        hook, so the first reader does not wait for it." No lifespan hook was
        ever written. The first narration therefore *does* pay it. Adding a
        warm-up hook is a real option, deliberately not taken: it would make
        `make dev` and every test fixture block on a model load even when the
        run never synthesises anything, and the tests inject `FakeSynthesizer`
        precisely to avoid that.
- If concurrency ever matters, the protocol is the seam: swap in an
  implementation that calls the `:8880` server, and nothing above it changes.
