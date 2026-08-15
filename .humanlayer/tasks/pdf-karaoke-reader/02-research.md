# Phase 2 — Research

Everything below was verified by running it on this machine, not read from docs.

## Toolchain

| Thing | Finding |
|---|---|
| Python (system) | 3.14.6 — too new for `kokoro-onnx` (`<3.14`). `uv` pins the API to **3.12**. |
| uv | 0.12.3. All Python work goes through `uv add` / `uv run` / `pyproject.toml`. |
| Node | nvm default is **22.10**, which pnpm 11 rejects (needs >= 22.13). Homebrew has **26.7.0** at `/opt/homebrew/opt/node/bin` → pnpm **11.20.0** works. |
| ffmpeg | 8.1.2 present (used to turn screenshot sequences into docs GIFs). |
| espeak-ng | **absent** — rules out the PyTorch `kokoro` package, which needs it as a system dependency. Reinforces the `fastkokoro`/ONNX choice. |

## `fastkokoro` 0.7.0

The package the goal calls "fast-kokoro". Verified installed under Python 3.12.

It ships **two** usable surfaces:

1. An OpenAI-compatible server (`fastkokoro` → `:8880`, `POST /v1/audio/speech`).
2. A direct in-process Python API:
   ```python
   FastKokoro().create(text, *, voice=None, speed=1.0,
                       response_format='mp3', lang=None) -> bytes
   ```

**Decision (revises Q2):** use the in-process API, not the sidecar. One fewer
process to supervise, and `response_format='wav'` gives us a frame count we can
read with the stdlib `wave` module — which is how we get an exact duration
without shelling out to ffprobe. Synthesis is CPU-bound, so the route offloads
it with `anyio.to_thread.run_sync`.

`am_adam` is confirmed present in the American English voice set
(`a` / `en-us` / `american`).

Useful extras discovered in its README: `[pause:1.5s]` inline tokens and
`[word](/phonemes/)` pronunciation overrides. Not needed for v1 but they are the
escape hatch if sentence pacing needs manual tuning.

## PyMuPDF word extraction — verified

`page.get_text("words")` returns tuples of
`(x0, y0, x1, y1, word, block_no, line_no, word_no)`:

```
(72.0, 84.9, 103.9, 104.2, 'Hello',  0, 0, 0)
(107.8, 84.9, 142.8, 104.2, 'brave',  0, 0, 1)
...
(72.0, 114.9, 119.5, 134.2, 'Second', 1, 0, 0)
```

Two things matter here:

- The tuple carries **both geometry and reading order**. Sorting by
  `(block_no, line_no, word_no)` gives reading order; the bbox gives us the
  highlight rectangle. We need no separate layout pass.
- PyMuPDF can also *create* a PDF (`new_page` + `insert_text`). That makes the
  **text → PDF → extract → text round-trip a property test**, with no fixture
  files to maintain. This is the single most valuable property in the codebase:
  it tests our extractor against arbitrary generated documents.

## Timing: the gap that defines the design

Neither `fastkokoro` nor the OpenAI speech API returns word timestamps. So the
karaoke timeline is **derived**, and derived code is exactly what property tests
are for. The pure function at the centre is:

```
allocate(words: list[str], duration: float) -> list[Span]
```

Its contract (→ becomes the property suite in phase 3):
covers `[0, duration]` exactly, no gaps, no overlaps, monotonic, one span per
word, order preserved, and total == duration to within float tolerance.

The client-side counterpart is equally pure:

```
activeIndex(timeline, t) -> number
```

which is binary search, property-tested in TypeScript against a linear scan.

## Tooling for the docs half

`chrome-mcp-server` is connected and exposes exactly what the docs need:
`chrome_screenshot`, `chrome_gif_recorder`, `chrome_upload_file` (drives the
drag-and-drop), `chrome_javascript`, `chrome_console`, `chrome_navigate`.

So UI verification and docs-artefact generation are the *same* action, which is
the property the goal asks for: docs images are test output.

## Property-based testing libraries

- Python: **Hypothesis** (already a dev dependency).
- TypeScript: **Hegel** (`@hegeldev/hegel`, 0.4.5) — same engine as Hypothesis
  via `libhegel`, so both sides shrink identically. It is beta; pin it.
  `hegel.test(fn, settings?)` returns `void` and runs immediately, so it must be
  wrapped as `test("...", () => hegel.test(...))`.
