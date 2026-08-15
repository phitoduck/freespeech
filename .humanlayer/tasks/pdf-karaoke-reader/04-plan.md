# Phase 4 — Plan

Each step ends at a checkpoint that can be run. Nothing is "done" until its
checkpoint passes.

| # | Step | Checkpoint |
|---|---|---|
| 1 | `domain/` — documents, sentences, timeline | `uv run pytest tests/properties` green |
| 2 | `services/extraction.py` + round-trip property | round-trip property green on generated PDFs |
| 3 | `services/speech.py` — protocol, fake, Kokoro | `uv run pytest -m kokoro` produces real audio |
| 4 | `app.py` `create_app()` + routes | `uv run pytest tests/bdd/test_api_*` green |
| 5 | Vite/React app, pnpm, Node 26 | `pnpm build` clean; app loads in Chrome |
| 6 | `lib/timeline.ts` + Hegel properties | `pnpm test` green |
| 7 | Wire UI: drop → pages → play → highlight | verified in Chrome via chrome-mcp-server |
| 8 | Playwright `@docs` scenarios → screenshots | images land in `docs/assets/generated/` |
| 9 | GIF of karaoke highlight | `docs/assets/generated/karaoke.gif` exists |
| 10 | Diátaxis site + 5 ADRs | `mkdocs build --strict` clean |
| 11 | `make dev` / `make test` / `make docs` | full suite from a clean checkout |

## Ordering rationale

Domain first (step 1) because the properties are the spec's sharp end and they
need nothing else to exist. Extraction second because its round-trip property
generates its own fixtures. The real model (step 3) comes before the API so that
the API is written against a synthesiser that is known to work. UI last, because
by then every guarantee it depends on has already been proved.

## Risks

- **Kokoro cold start is 18s** (model load). Mitigation: warm the engine in a
  FastAPI lifespan hook and keep it as a module singleton; the fake synthesiser
  keeps the test suite off the model entirely.
- **Per-sentence synthesis is serial.** A dense page could take several seconds.
  Mitigation: synthesise per page on demand, cache by `(doc, page, voice)`.
- **Hegel is beta.** Pin exactly; if it breaks, the TS properties are small
  enough to port to fast-check without touching the tested code.
