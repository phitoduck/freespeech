# Phase 5 — Implementation

## How code gets written here

Every unit of work passes through three *separate* agents. Separation is the
point: an agent that writes both the test and the code writes a test that
describes what it happened to build.

| Agent | May write | May NOT | Contract |
|---|---|---|---|
| **test-author** | `tests/`, `*.test.ts` | read the implementation under test | Writes from `features/*.feature` and `03-design.md` only. Failing tests are a valid deliverable. |
| **implementer** | source | edit or weaken a test | Makes the red green. If a test looks wrong, implement to it and report — never edit it. |
| **test-critic** | may delete tests | write implementation | Prunes any test that cannot fail for a real reason. |

Red before green is enforced by evidence, not honour: the test-author reports the
failure output, and the failure has to be the *expected* one (a missing module,
not a typo).

## The pyramid

Wide at the bottom, and every level tests something the level below cannot.

| Level | Where | Runs against | What only it can catch |
|---|---|---|---|
| **Properties** | `tests/bdd/test_*_properties.py`, `src/lib/timeline.test.ts` | pure functions | Timeline invariants over generated input — the guarantees the highlight rests on |
| **Unit invariants** | `tests/properties/` | pure functions | Internal contracts not visible as behaviour (`split_sentences` losing no words) |
| **Service** | `tests/services/` | PyMuPDF, Kokoro | That the real libraries behave as assumed; one `@kokoro` test on the real model |
| **Contract** | `tests/contract/` | `create_app()` + `FakeSynthesizer` | The HTTP shape the frontend codes against |
| **Component** | `apps/web/src/**/*.test.tsx` | React + jsdom | Rendering and interaction without a server |
| **End-to-end** | `tests/bdd/test_*_ui.py` | real browser, real API, real Kokoro | That the parts are wired together at all — and it produces the docs screenshots |

The distributed seams are the interesting ones, and each has a test that only
exists because the seam does: browser↔API (contract + E2E), API↔PyMuPDF
(service), API↔Kokoro (service, marked), and the derived-timeline seam between
audio and highlight (properties, both sides of the wire).

## Status

- ✅ `domain/` — documents, sentences, timeline. Doctested, ruff-clean.
- ✅ `services/` — extraction (PyMuPDF round-trip), speech (Fake + Kokoro).
- ✅ `create_app()` + routes, with HTTP byte-range support.
- ✅ React UI — drop, extract, narrate, highlight, click-to-seek.
- ✅ ADRs 0001–0005, Diátaxis site written.
- ✅ Playwright `@docs` scenarios, docs screenshots and GIF.
- ✅ Property strengthened for the unreachable-guard finding.

Counts live in **Final state** below, so they are stated once.

**Verified working end to end in a real browser**, against the real model:
a dropped PDF yields 27 words, 8.69s of `am_adam` audio (peak amplitude 30080,
so genuinely speech), and the highlight tracks it — `t=0`→"The"(0),
`t=3.5`→"reads"(10), `t=6.5`→"Each"(19), `t=8.6`→"spoken."(26), always exactly
one word active.

## Bugs the process caught

Worth recording, because each was caught by a specific level of the pyramid and
by no other:

| Bug | Found by | Why nothing below it caught it |
|---|---|---|
| Audio route served no HTTP byte ranges → `audio.seekable == [0, 0]`, click-to-seek silently dead | driving a real browser | the contract test asserted `200` + `audio/wav`, and both were true |
| Drop zone had no `<input type="file">` — mouse-only, unreachable by keyboard or AT | driving a real browser | the component test only covered the drop path, so the implementer built only that |
| `allocate`'s `nextafter` guard is unreachable | mutation testing by the critic | the `durations` strategy was bounded at 0.05s, which avoids the exact regime the guard defends |
| `error::DeprecationWarning` + PyMuPDF's SWIG bindings **segfaults** the interpreter mid-C-extension-import | running the suite at all | nothing — but the failure looks like a pymupdf bug rather than a config bug, so it is worth writing down |
| `uv sync --group docs` prunes the `tts` extra and silently breaks the real-model test | running the suite after a docs install | fixed with `default-groups`; the lesson is that `uv sync` is a *set*, not an *add* |
| Clicking a word highlighted the *previous* word — the browser snaps a seek down to a frame boundary, landing just before `span.start` | end-to-end scenario | it is a property of real media elements; no unit, component or contract test can see it. Fixed by seeking `min(10ms, span/2)` into the word |
| Playwright's Chromium was never installed, so the whole E2E level would have failed at first launch | checking a dependency before trusting an agent | — |
| **Stale narration overwrote a newer page** — press Next twice and the slower response wins, leaving one page's words on screen with another page's audio | forcing the race with a delayed route | every level below asserts within *one* page; nothing checked that words and audio describe the *same* page. Fixed with a monotonic request token |
| A scanned PDF (no text layer) was accepted silently: blank page, enabled play button, no explanation | trying an input nobody had tried | all fixtures were `render()`-generated and always had text |
| Page navigation did not exist — the API served every page, the UI only ever read `doc.pages[0]` | trying a 2-page PDF | no test or scenario mentioned a second page, so nothing was missing from any suite's point of view |
| **A 262-word synthesis unit** in real documents — bullet lists, headings and CVs carry no full stop, so `split_sentences` never split. ADR 0002's "error is bounded by the sentence" was materially false | running real PDFs through the domain | every word generator produced punctuated text |
| The drift property was **self-referential** — it imported `MAX_UNIT_WORDS` from the code under test, so raising the cap to 10000 kept it green | mutation-testing a fix minutes after shipping it | the test was written to my own instruction, which said to assert against the imported constant. My error, in the cycle where I was cataloguing this exact pattern |
| `word_lists` declared `st.lists(max_size=60)` but measured p99=29 and reached 60 in **0 of 15,000** draws, leaving `allocate`'s collision regime ~32% likely to get zero coverage per run | measuring every strategy's real distribution | the declaration looked right; only sampling showed it was not |
| A password-protected PDF was reported as "not a valid PDF", and the corrupt-file message read "not a valid PDF: not a valid PDF" | trying an encrypted PDF | no fixture was ever encrypted; the doubling only became user-visible once the UI started surfacing the API's `detail` |
| Three byte-identical orphan screenshots sat in `docs/`, while my ad-hoc orphan check reported none — it matched **basenames**, so four copies of `01-empty.png` all "matched" one reference | fixing the check | the check was structurally incapable of finding them |

## The pattern under half of these

Seven of the sixteen share one shape: **a check that could not fail.** The
`nextafter` guard behind a duration floor; punctuated-only generators hiding a
262-word unit; `word_lists` never reaching its declared ceiling; a property
importing its own bound; an orphan check matching basenames; and — twice — my
own ad-hoc shell verification, which is the code that never gets a guard because
it is not code.

Naming the pattern did not prevent it. I instantiated it myself one cycle after
writing it down. What worked was making it mechanical: mutation testing,
`tests/properties/test_strategies_cover_their_range.py` (strategies must reach
their declared ranges), and `tests/docs/test_generated_images.py` (no orphans,
no byte-identical duplicates) — each one proven to go red before being trusted.

The rule worth keeping: **a negative result is evidence only once the check has
been shown capable of a positive one.**

The `nextafter` finding is the clearest instance: the test had been written to
avoid the hard case, and only deliberately breaking the implementation revealed
it. Widening `durations` down to `1e-323` immediately produced a minimal
counterexample — `allocate(["0","0","0"], 1e-323)` yields
`Span(word_index=1, start=5e-324, end=5e-324)`, a zero-length span — and with
the guard restored the property passes. The blind spot is closed, and the guard
is now load-bearing rather than decorative.

## The one thing that beat us

Partway through the session this machine's Chromium stopped advancing
`<audio>.currentTime` entirely — it worked earlier, then didn't. Proved
environmental two independent ways: a 440 Hz WAV as a `data:` URI with no
server, and a synthesised WAV over a bare `python3 -m http.server`, both freeze
at 0.042667s (one 1024-sample buffer) with `readyState: 4`, fully buffered, no
error, `paused: false`. Headed, headless, `--mute-audio`,
`--disable-features=AudioServiceOutOfProcess` and fake-device flags all behave
identically.

The end-to-end scenario now drives the playhead itself and asserts the
highlight follows, with the limitation written into
`docs/explanation/testing-strategy.md` rather than buried. Real playback *was*
verified working earlier in the session (`t=2.24` "lazy", `t=3.15` "Kokoro",
`t=8.57` "spoken."), so the app is fine; the harness is what had to adapt.

## Final state

Totals are deliberately not written down here — they went stale three times
while this document was being kept up to date, which is its own small lesson.
The shape is what is worth recording:

| Level | Where |
|---|---|
| Properties (Hypothesis / Hegel) | `tests/bdd/*_properties.py`, `apps/web/src/lib/timeline.test.ts` |
| Unit invariants | `tests/properties/` |
| Service | `tests/services/` — one test on the real model, marked `kokoro` |
| Contract | `tests/contract/` — `create_app()` + `FakeSynthesizer` |
| Component | `apps/web/src/components/*.test.tsx` |
| End-to-end | `tests/bdd/*_ui.py` — real browser, real model, writes the docs images |

For the current numbers, run them:

```bash
uv run pytest -q --collect-only | tail -1     # Python tests
cd apps/web && pnpm test                      # TypeScript tests
grep -c 'Scenario:' features/*.feature        # Gherkin scenarios
```

`ruff check .`, `tsc -b` and `mkdocs build --strict` are all clean, and the
suite has run green on consecutive invocations at identical timing.
- `mkdocs build --strict` passes — every image the docs reference is produced by
  a passing scenario.
- Click-to-seek verified in a real browser: clicking words 3, 10, 19 and 26 each
  highlight exactly that word.

## Notes for whoever picks this up

- Node: `export PATH=/opt/homebrew/opt/node/bin:$PATH` — the nvm default (22.10)
  is too old for pnpm 11. `.nvmrc` pins 26.7.0.
- pnpm's `verifyDepsBeforeRun` is off in `pnpm-workspace.yaml`; without it every
  `pnpm run` re-runs install and fails on native-build approval for `koffi`,
  whose binary is prebuilt anyway.
- The real model is an optional extra: `uv sync --extra tts`.
