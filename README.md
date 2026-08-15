# Karaoke PDF Reader

Drop a PDF. Adam reads it aloud, and each word lights up as he says it.

Everything runs locally — the voice is [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M),
an 82M-parameter model that synthesises speech on a laptop CPU. No account, no
upload, no API key.

```bash
make install     # uv + pnpm + chromium + the Kokoro model
make dev         # API on :8000, web app on :5173
```

## The interesting problem

Kokoro returns audio samples and nothing else — no timestamps. So the word
timeline is **reconstructed**: each sentence is synthesised separately (its
duration is therefore *measured*), and that duration is divided among the
sentence's words in proportion to how long each ought to take to say.

Units are also capped at 24 words, because real documents — bullet lists,
headings, CVs — often contain no full stop at all, and one measured 262-word
"sentence" anchors nothing. Estimation error is confined inside a unit and
never accumulates down a
page. The details are in
[docs/explanation/timing.md](docs/explanation/timing.md).

Because the timeline is derived, every guarantee the highlight depends on is
proved rather than assumed — stated in Gherkin, checked against generated input:

```gherkin
@property
Scenario: Any page's timeline covers its audio exactly once
  Given any page of words and any audio duration
  When a timeline is built for them
  Then the spans are in ascending order
  And no two spans overlap
  And there are no gaps between spans
  And the first span starts at 0.0
  And the last span ends at the audio duration
```

## How this was built

Behaviours first, in `features/`. A scenario is either an **example**
(`@docs`, concrete nouns, becomes documentation) or a **property**
(`@property`, uses the word *any*, runs against generated input). The
quantifier lives in the Gherkin where a non-programmer can see it.

Tests are written by an agent that has not seen the implementation; a second
agent makes them pass and may never edit a test; a third prunes tests that
cannot fail for a real reason. That separation is not ceremony — it caught two
bugs that a single author would have missed:

- the audio route served no HTTP byte ranges, so `audio.seekable` was `[0, 0]`
  and click-to-seek silently did nothing. The contract test asserted `200` and
  `audio/wav`, and both were true.
- the drop zone had no file input at all, so it was mouse-only and unreachable
  by keyboard or assistive tech.

And a mutation test found a guard in `allocate()` that no property could reach,
because the strategy had been bounded to avoid the exact regime the guard
defended.

## Layout

```
apps/api/      FastAPI (create_app), uv, Python 3.12
  domain/      pure — documents, sentences, timeline
  services/    PyMuPDF extraction, Kokoro speech behind a Protocol
apps/web/      Vite + React + TypeScript, pnpm
features/      Gherkin — the shared vocabulary
tests/         properties, services, contract, end-to-end
docs/          Diátaxis site; Reference is generated from the test run
```

## Commands

```bash
make test        # everything that needs neither a browser nor the model
make test-kokoro # the one test that loads the real model
make test-e2e    # browser scenarios; regenerates the docs screenshots
make docs        # build the Diátaxis site
```

## Notes

- Python is entirely uv-managed: `uv add`, `uv run`, `pyproject.toml`.
- Node 22.13+ is required by pnpm 11. `.nvmrc` pins 26.7.0; the `Makefile`
  prepends `/opt/homebrew/opt/node/bin` so your shell does not have to.
- The Kokoro model is an optional extra (`uv sync --extra tts`). The test suite
  substitutes a deterministic fake and never downloads it.
