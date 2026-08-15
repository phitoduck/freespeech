# How the karaoke timing works

The reader highlights the word being spoken. To do that it needs, for every word
on the page, the moment the narrator starts saying it and the moment they stop.

Kokoro does not tell us. It takes text and returns audio samples — no timestamps,
no token boundaries, nothing. So the timeline is **reconstructed**, and this page
explains how, and how far you can trust it.

## The trick: measure sentences, estimate words

The page is split into sentences, and **each sentence is synthesised as its own
request**. That single decision is what makes the result trustworthy.

When a sentence comes back, we know its duration exactly — a WAV header carries a
frame count and a sample rate, and the division is not an estimate. So every
sentence boundary in the timeline is a *measured* value.

Inside a sentence, we estimate. The sentence's measured duration is divided among
its words in proportion to how long each word ought to take to say:

```
cost(word) = 0.05                       if nothing is said for it at all
           = 1.0                        otherwise: every word takes some time
           + 0.55 x vowel groups        syllables dominate speaking time
           + 0.08 x letters             long words take longer, syllables equal
           + 0.65 x digits              each digit is read as its own word
           + 0.9 after . ! ?            the narrator breathes
           + 0.4 after , ; :            a shorter breath
```

Then each word gets `duration x cost / total_cost`, laid end to end.

!!! note "Costed on what is said, not on what is printed"
    Some tokens are pure layout. A table-of-contents leader —
    `Introduction..........7`, one token straight out of the PDF — and a bare
    bullet glyph are both stripped before Kokoro sees them, because it would
    otherwise read the dots aloud one by one. They are still *on the page* and
    still get highlighted, so they still need a span; but pricing them at the
    full base cost gave a silent 10-dot leader **1.78s of a 7.21s unit**, and
    the highlight sat there while the voice moved on.

    So cost is measured on the same stripped form the synthesiser receives. The
    leader now costs 0.05 and gets a 0.06s flicker. As a side effect `Wait....`
    no longer earns the 0.9 sentence pause: it is spoken as "Wait", with no full
    stop to breathe after.

!!! note "Why digits count separately"
    They were missed at first, and it mattered. The letter class is
    `[^\W\d_]`, which *excludes* digits, so every number scored the bare base
    cost: `2024`, `1250000` and `2024-08-15` all came to exactly 1.00 — less
    than the word "we" at 1.71 — while taking seconds to speak. In real PDFs
    **11% of tokens contain no letters at all**: dates, times, prices,
    quantities.

    The weight is set just above `0.55 + 0.08` — what the one-letter word "a"
    costs — because a digit is spoken as its own small word: "2024" is "twenty
    twenty-four", four digits and about four syllables. Landing exactly on
    0.63 was tried first and rejected: `1.0 + 0.63` and `1.0 + 0.55 + 0.08` are
    the same number but associate differently in floating point and can end up
    a ULP apart, so a bare digit came out *fractionally* cheaper than a letter.
    0.65 gives real headroom instead of relying on a tolerance.

    On a real CV, digit tokens are 12.4% of the words and now receive 9.2% of
    the speaking time — proportionate, where before they received almost none.

!!! note "Why units, and why they are capped"
    Estimation error does not accumulate. Every unit boundary re-pins the
    timeline to a measured value, so a bad guess about the word "Worcestershire"
    can push the highlight around *within* its unit and nowhere else. Across a
    400-word page, the highlight never drifts away from the voice.

    That argument only holds while units stay short — and sentences do not.
    Real documents are full of text with no full stop: bullet lists, headings,
    table cells, CVs. Splitting on `.!?` alone produced a **262-word** unit from
    a real CV, about eighty seconds of audio anchored exactly once at each end.
    So a unit is additionally capped at `MAX_UNIT_WORDS` (24), split at a comma,
    semicolon, dash or bullet where one exists inside the window and hard-split
    only where a run offers nothing. Each split is an audible pause, which is
    why the boundary is preferred rather than chopping every 24 words flat.

## What this buys, and what it costs

You get word-level highlighting with one model, no aligner, and no second
inference pass. What you give up is sub-word accuracy: inside a sentence, a
highlight can land a fraction of a word early or late. Following along while
listening, you will not notice. Producing broadcast subtitles, you would.

[ADR 0002](adr/0002-derive-word-timings-per-sentence.md) records the alternatives
that were weighed and why this one won.

## Why the guarantees are proved, not assumed

The UI leans on the timeline harder than it looks. "Highlight the current word"
quietly assumes that at every instant there is *exactly one* current word — which
is only true if the spans cover the audio with no gaps, no overlaps, and no word
allotted zero time.

None of that is automatic for derived data. Round a boundary the wrong way and
two words are lit at once; let a float drift and the last word ends before the
audio does and the highlight freezes early.

So `allocate()` is written so the guarantees hold **by construction**:

- spans are laid end to end — `start[i+1]` *is* `end[i]`, the same float. Gaps and
  overlaps are not unlikely, they are unrepresentable.
- the final boundary is assigned the measured duration itself rather than a
  cumulative sum, so the timeline ends exactly where the audio does.
- every word carries a positive cost — a full base cost, or 0.05 if nothing is
  said for it — so no span can be empty.

And then the properties in
[`features/karaoke.feature`](../reference/behaviours.md) hold it to account
against generated input — arbitrary pages, arbitrary durations, hundreds of cases
per run:

> **Scenario: Any page's timeline covers its audio exactly once**
> Given any page of words and any audio duration
> When a timeline is built for them
> Then the spans are in ascending order
> And no two spans overlap
> And there are no gaps between spans
> And the first span starts at 0.0
> And the last span ends at the audio duration

That is a sentence you can read without knowing Python, and it is also the test.

## The same function, twice

The browser asks a related question sixty times a second: *given the audio is at
`t`, which word is that?* That is `word_at` in Python and `activeIndex` in
TypeScript — the same binary search, written twice because it runs on both sides
of the wire.

Both are property-tested against a linear scan, which is the strongest available
statement about a binary search: it agrees with the obvious implementation on
every input anyone can generate. Python uses Hypothesis; TypeScript uses Hegel,
which is built on Hypothesis and shrinks counterexamples identically — so a bug
found on one side reduces to the same minimal case on the other.
