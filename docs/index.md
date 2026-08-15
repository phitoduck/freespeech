# Karaoke PDF Reader

Drop a PDF onto the page. Adam reads it aloud, and each word lights up as he says
it, so you can follow along by eye and ear at once.

It runs entirely on your machine. No account, no upload, no API key — the voice is
[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), an 82M-parameter model that
synthesises speech on a laptop CPU.

<div class="grid cards" markdown>

- :material-play-circle: **[Read your first PDF aloud](tutorials/read-your-first-pdf.md)**

    Start here. From a clean checkout to hearing a page read, in about ten
    minutes — most of which is a model download.

- :material-tools: **[How-to guides](how-to/change-the-voice.md)**

    Change the voice, regenerate the documentation screenshots, add a behaviour.

- :material-book-open-variant: **[Reference](reference/behaviours.md)**

    Every behaviour, the HTTP API, and the interface screen by screen. Generated
    from the test run, so it cannot drift.

- :material-lightbulb: **[Explanation](explanation/timing.md)**

    How the karaoke timing works when the model gives us no timestamps, the
    testing strategy, and the decisions behind both.

</div>

## The interesting problem

Kokoro returns audio samples and nothing else. No timestamps, no token
boundaries. To highlight the word being spoken, the reader has to reconstruct the
timeline — and then *prove* the reconstruction is sound, because the interface
quietly assumes that at every instant there is exactly one current word.

That assumption is not free. It requires the spans to cover the audio with no
gaps, no overlaps, and no word given zero time. So it is stated as a behaviour,
in a language you can read without knowing Python:

```gherkin
Scenario: Any page's timeline covers its audio exactly once
  Given any page of words and any audio duration
  When a timeline is built for them
  Then the spans are in ascending order
  And no two spans overlap
  And there are no gaps between spans
  And the first span starts at 0.0
  And the last span ends at the audio duration
```

That is a property test — hundreds of generated pages per run, shrunk to a
minimal counterexample when it fails. It is also the specification.
[How the karaoke timing works](explanation/timing.md) explains the rest.
