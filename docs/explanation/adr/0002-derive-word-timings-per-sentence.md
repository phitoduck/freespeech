# 2. Derive word timings from per-sentence synthesis

- Status: accepted
- Date: 2026-08-15

## Context

The karaoke highlight needs `(word, start, end)`. Kokoro returns audio samples
and nothing else — there is no timestamp API, and the OpenAI-compatible speech
endpoint `fastkokoro` implements has no field for one.

Three ways to get timings:

1. **Forced alignment** — run an aligner (e.g. WhisperX, MFA) over the generated
   audio. Accurate to the word. Adds a second model, a second inference pass, and
   several hundred MB.
2. **A model that emits durations** — the PyTorch `kokoro` package exposes
   per-token `start_ts`/`end_ts` through `KPipeline`. Accurate, but it pins
   `python<3.13` and needs a system `espeak-ng`, which is not installed here.
3. **Derive them** — synthesise a sentence, measure its exact duration, and split
   that duration across the sentence's words by an estimate of how long each
   takes to say.

## Decision

Option 3, at **sentence** granularity.

Each sentence is synthesised as its own request, so its duration is *measured*,
not estimated. Within a sentence, `allocate()` divides the measured duration in
proportion to a per-word speech cost (base + syllables + letters + a pause
weight for trailing punctuation).

## Consequences

- **Error is bounded by the synthesis unit**, and units are bounded to
  `MAX_UNIT_WORDS` (24). Drift cannot accumulate down a page,

    !!! warning "Corrected 2026-08-15"
        This originally said error was bounded **by the sentence**, full stop.
        That was false for real documents. Bullet lists, headings, table cells
        and CVs carry no terminal punctuation, so splitting only on `.!?`
        produced units of 50, 90, 109 and — measured on a real CV — **262
        words**: roughly eighty seconds of audio in one utterance, every word's
        timing estimated with no measured re-anchor whatsoever. Across four real
        PDFs, 10 of 46 units exceeded 30 words.

        `split_sentences` now also splits on length, preferring a natural
        boundary (comma, semicolon, dash, bullet) inside the window and
        hard-splitting only where a run has none. The same four PDFs now yield
        0 units over 30 words, longest 24. The guarantee below is true because
        of that cap, not because sentences are naturally short.
  because every sentence boundary is re-pinned to a measured value. This is the
  whole reason for the per-sentence split.
- Within a sentence, a word's highlight can be early or late by a fraction of a
  word. For following along while listening, this is not noticeable; for
  subtitle-grade alignment it would be.
- The timeline is now *derived data*, so every guarantee the UI depends on has to
  be proved rather than assumed. `allocate()` is written so those guarantees hold
  by construction — spans are laid end to end, and the final boundary is assigned
  the measured duration itself — and the `@property` scenarios in
  `features/karaoke.feature` hold it to account against generated input.
- More HTTP round trips to the synthesiser: one per sentence, not one per page.
  Acceptable locally; would want batching over a network.
- Reversible. `allocate()` is one function behind a stable signature; swapping in
  forced alignment means replacing its body, not the architecture.
