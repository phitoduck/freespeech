"""Contract tests for the SpeechSynthesizer implementations."""

from __future__ import annotations

import pytest
from reader.domain.sentences import Sentence
from reader.services.speech import FakeSynthesizer, KokoroSynthesizer, wav_duration


def test_wav_duration_is_positive_for_non_empty_text():
    wav_bytes = FakeSynthesizer().synthesize("hello world", voice="am_adam")

    assert wav_duration(wav_bytes) > 0


def test_wav_duration_is_deterministic_for_the_same_text():
    synth = FakeSynthesizer()

    first = wav_duration(synth.synthesize("hello world", voice="am_adam"))
    second = wav_duration(synth.synthesize("hello world", voice="am_adam"))

    assert first == second


@pytest.mark.kokoro
def test_kokoro_synthesizer_returns_a_wav_of_positive_duration():
    wav_bytes = KokoroSynthesizer().synthesize("Hello, this is a test.", voice="am_adam")

    assert wav_duration(wav_bytes) > 0


@pytest.mark.kokoro
def test_kokoro_gives_positive_duration_for_an_all_bullet_units_fallback_text():
    """timeline.allocate() raises ValueError on a non-positive duration, so
    whatever Sentence.text falls back to for an all-bullet unit (e.g.
    words=("●", "▪")) must be BOTH glyph-free (it must not make the narrator
    say "black circle") AND actually vocalised by the real model --
    "textually non-empty and glyph-free" is not the same property as
    "audible", and FakeSynthesizer (which returns a fixed 0.05s for any
    input, including "") cannot tell the two apart.

    Measured directly against KokoroSynthesizer.synthesize(voice="am_adam"):
        ""       -> 0.0s
        "-"      -> 0.0s   (a bare hyphen is nothing to say)
        "•" -> 0.0s   (small bullet "•" -- silent even though it's a glyph)
        "●" -> 0.99s  (black circle "●")
        "▪" -> 1.29s  (black square "▪")
        "bullet" -> 0.86s  (an ordinary word -- always audible)

    Decision (test-critic adjudication): the fallback must be a real,
    non-glyph word -- e.g. "bullet" -- not the original glyphs. The
    alternative (fall back to the unstripped glyphs, e.g. "●"/"▪",
    which ARE audible at 0.99-1.29s) was rejected: it reintroduces the exact
    narrator-says-a-glyph-name behavior this whole fix exists to prevent,
    for a marginal gain (a "real" word vs. a placeholder) that only matters
    for a unit shape that occurred zero times across 9 real PDFs. It's also
    not fully general: "•" is silent too, so "fall back to the glyphs"
    still crashes when the unit is entirely "•" characters.

    As of this test's authoring, Sentence.text's fallback for an all-bullet
    unit is the literal "-" (`spoken or "-"` in
    apps/api/src/reader/domain/sentences.py), which is silent to the real
    model -- so this test is expected to FAIL until that fallback is
    changed. If it is red: change the `spoken or "-"` fallback in
    Sentence.text to `spoken or "bullet"` (or another ordinary word you
    confirm is audible), NOT back to the raw glyphs. Do not "fix" this by
    relaxing the assertions below; the whole point is that allocate()
    crashes on 0.0s durations.
    """
    text = Sentence(start=0, words=("●", "▪")).text
    wav_bytes = KokoroSynthesizer().synthesize(text, voice="am_adam")

    assert not any(glyph in text for glyph in "●•▪"), (
        f"Sentence.text fallback {text!r} still contains a bullet glyph -- "
        "the narrator would speak its name"
    )
    assert wav_duration(wav_bytes) > 0, (
        f"Sentence.text fallback {text!r} produced silence from the real "
        "model -- timeline.allocate() would raise ValueError on this duration"
    )
