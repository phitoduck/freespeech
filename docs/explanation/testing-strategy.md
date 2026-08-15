# Testing strategy

This project is partly an experiment in a way of working, so the test suite is
designed rather than accumulated. Two ideas do most of the work.

## 1. The Gherkin carries the quantifier

A property test is a Scenario Outline whose Examples table is generated at
runtime and minimised on failure. Once you see it that way, behaviour-driven
specs and property-based tests stop competing.

The distinction lives in the **wording of the scenario**, where a
non-programmer can see it:

=== "An example"

    ```gherkin
    @docs
    Scenario: Dropping a one-page PDF reveals its text
      Given a PDF containing the text "The quick brown fox..."
      When I drop it onto the drop zone
      Then the reader shows 1 page
    ```

=== "A property"

    ```gherkin
    @property
    Scenario: Any text survives the round trip through a PDF
      Given any document of words
      When it is rendered to a PDF and extracted again
      Then the extracted words are exactly the original words, in order
    ```

The word **"any"** is the universal quantifier. `@docs` scenarios are written
examples and become the documentation; `@property` scenarios are generated and
never appear in the docs, because a hundred shrunk random cases make excellent
tests and terrible reading.

### How they run together

The naive combination — Hypothesis's `@given` on a pytest-bdd `@scenario` — is
broken. pytest-bdd builds a scenario out of fixtures, and Hypothesis re-runs the
body many times per fixture setup, so `Given` steps would run once while a
hundred examples chewed on the same state.

So the property runs **inside a step**:

```python
from hypothesis import given as for_all   # reads as what it is

@given("any page of words and any audio duration", target_fixture="subject")
def _():
    return pages_with_duration()          # a strategy, not a value

@when("a timeline is built for them", target_fixture="operation")
def _():
    return lambda words, duration: allocate(words, duration)

@then("no two spans overlap")
def _(subject, operation):
    @for_all(subject)                     # all examples run inside ONE step
    def property_holds(case):
        words, duration = case
        spans = operation(words, duration)
        assert all(a.end <= b.start for a, b in zip(spans, spans[1:]))

    property_holds()
```

[ADR 0005](adr/0005-gherkin-quantifiers-split-examples-from-properties.md) records
why.

## 2. Tests are written by someone who has not seen the code

Every unit of work passes through three agents that cannot do each other's jobs:

| | writes | may not |
|---|---|---|
| **test-author** | the tests | read the implementation under test |
| **implementer** | the code | edit or weaken a test |
| **test-critic** | deletions | write implementation |

The test-author works from `features/*.feature` and the design doc alone. This
is not ceremony — it changes what gets written. A test derived from the code
describes what the code happens to do; a test derived from the spec describes
what it is supposed to do, and the difference between the two is where the bugs
live.

The implementer's constraint matters just as much. Early on, three TypeScript
property tests failed; the implementer diagnosed the cause as a bug in the *test*
(Hegel rejects `allowInfinity` combined with explicit bounds) and reported it
rather than editing it. The test-author fixed its own generator, and all four
properties then ran and passed. Had one agent owned both, the likely outcome was
a quietly narrowed generator and a property that no longer tested infinities.

The critic then prunes. Its standard is a single question: *what plausible bug
does this test catch that no other test catches?* Tests with no answer are
deleted, and properties are checked by deliberately breaking the implementation
to confirm they notice.

## The pyramid

| Level | Runs against | What only it can catch |
|---|---|---|
| Properties | pure functions | Timeline invariants over generated input |
| Unit invariants | pure functions | Contracts not visible as behaviour |
| Service | PyMuPDF, Kokoro | That the real libraries behave as assumed |
| Contract | `create_app()` + a fake synthesiser | The HTTP shape the frontend codes against |
| Component | React + jsdom | Rendering and interaction, no server |
| End-to-end | browser + API + real model | That the parts are wired together — and it produces the docs screenshots |

The seams get the attention, because a distributed system fails at its joins:
browser↔API, API↔PyMuPDF, API↔Kokoro, and the derived-timeline seam between the
audio and the highlight — which is tested on both sides of the wire, in Python
with Hypothesis and in TypeScript with Hegel.

## What the model does and does not touch

The real Kokoro model is an optional extra. `FakeSynthesizer` returns a genuine
but silent WAV whose length is a deterministic function of the text, so the whole
suite runs offline in seconds. Exactly one test, marked `@pytest.mark.kokoro`,
exercises the real thing — and the end-to-end scenarios use it, because a
narration nobody has heard is not evidence of anything.

```bash
make test          # needs neither a browser nor the model — seconds, not minutes
make test-kokoro   # the one test that loads the real model
make test-e2e      # browser scenarios; regenerates the documentation screenshots
make test-all      # everything, browser and model included
```

Counts are deliberately not written here. They were stated three times and were
wrong within minutes on each occasion — twice because another change landed
while the sentence was being written. For the current numbers, ask the suite:

```bash
uv run pytest -q --collect-only | tail -1
grep -c 'Scenario:' features/*.feature
```

## One thing the tests do not exercise

The end-to-end scenarios press play and assert that playback really starts —
`audio.paused` becomes false — but they then **drive the playhead themselves**
rather than waiting for the audio clock to advance.

That is not a preference. On this machine Chromium never advances
`currentTime`: a bare 440 Hz WAV in a plain `<audio>` element, with no server,
no React and no API involved, freezes at 0.042667s — exactly one 1024-sample
buffer — while reporting `readyState: 4`, the whole file buffered, and no
error. It is the audio output stack, not anything in this project.

So the harness advances the playhead at real speed and asserts the highlight
follows. What this project promises is the *mapping* from playhead to
highlight; Chromium's audio renderer is not ours to test. The gap is worth
naming plainly: **if the browser stopped advancing the clock during real
playback, no test here would notice.** Catching that needs a machine with a
working audio device, and on one the same scenario passes unchanged — the
highlight was observed tracking real playback at `t=2.24` "lazy",
`t=3.15` "Kokoro", `t=8.57` "spoken.".
