"""Sentence.text must not hand the synthesiser a glued-on bullet glyph. The
displayed word (Sentence.words) keeps it -- only the spoken text changes.

>>> Sentence(start=0, words=("●Set", "up")).text
'Set up'
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given
from reader.domain.sentences import Sentence

_BULLET_GLYPHS = "●•▪"

# Measured directly against the real KokoroSynthesizer (voice="am_adam"); the
# `kokoro`-marked test in tests/services/test_speech.py has the full readout.
# Kokoro produces 0.0s of audio for every one of
# these -- timeline.allocate() raises ValueError on that duration, so a
# fallback that lands on any of them is a silent 500, even though it is
# non-empty and (for "-") glyph-free.
_MEASURED_SILENT_IN_KOKORO = frozenset({"", "-", "•"})


@pytest.mark.parametrize("glyph", list("●▪•"))
def test_a_glued_bullet_is_dropped_from_the_spoken_text(glyph):
    """A bullet glued to the front of a word is dropped from .text, but
    .words still carries it -- the page keeps showing it.

    Sentence(start=0, words=("●Set", "up")).text -> 'Set up'.
    """
    sentence = Sentence(start=0, words=(f"{glyph}Set", "up"))

    assert sentence.text == "Set up"
    assert sentence.words == (f"{glyph}Set", "up")


def test_hyphen_is_not_a_bullet_and_survives():
    """A leading hyphen is a legitimate word character ("well-known", "-5"),
    and the model already says nothing for it -- stripping it would be both
    wrong and pointless.

    Sentence(start=0, words=("well-known", "-5")).text -> 'well-known -5'.
    """
    assert Sentence(start=0, words=("well-known", "-5")).text == "well-known -5"


def test_a_token_that_is_only_a_bullet_leaves_no_stray_space():
    """A bare bullet contributes nothing to speech, but naive stripping
    (turning it into "") then joining with " " leaves a double space or a
    leading space. It must not.

    Sentence(start=0, words=("●", "Set", "up")).text -> 'Set up'.
    """
    sentence = Sentence(start=0, words=("●", "Set", "up"))

    assert sentence.text == "Set up"
    assert "  " not in sentence.text


def test_a_unit_of_only_bullets_still_yields_speakable_text():
    """speech_cost / allocate raise ValueError on a non-positive duration, so
    a unit whose .text is empty (or whitespace-only) is a real 500 -- the
    synthesizer gets nothing to say and produces a zero-length clip.

    Contract chosen here: Sentence.text is never empty, nor whitespace-only,
    while .words is non-empty -- whatever the fallback is (e.g. leaving an
    all-bullet word unstripped rather than deleting it), the pipeline must
    always have something to synthesize.

    NOTE this is necessary but NOT sufficient: a non-empty, glyph-free string
    can still be silent to the real model (Kokoro reads a bare "-" as 0.0s of
    audio, same as ""), and this test's FakeSynthesizer-free assertion below
    cannot detect that -- only a synthesizer can. See the kokoro-marked
    test in tests/services/test_speech.py, which exists because a "-"
    fallback once shipped green here: silent, but non-empty and glyph-free.

    Sentence(start=0, words=("●", "▪")).text.strip() -> non-empty.
    """
    sentence = Sentence(start=0, words=("●", "▪"))

    assert sentence.text.strip() != ""


def test_a_unit_of_only_bullets_does_not_fall_back_to_a_known_silent_token():
    """Non-emptiness alone is not proof of audibility: the real model was
    measured to produce 0.0s of audio for "", "-", and "•" alike (see
    _MEASURED_SILENT_IN_KOKORO above), so `.text.strip() != ""` does not
    rule out a fallback that still crashes allocate(). This is a fast,
    kokoro-free pin against exactly the regression that shipped once
    already: falling back to "-".

    It is necessary but not sufficient -- it cannot prove a *new* fallback
    word is audible, only that it isn't one of the ones already measured
    silent. The authoritative check is the kokoro-marked
    test_kokoro_gives_positive_duration_for_an_all_bullet_units_fallback_text
    in tests/services/test_speech.py, which calls the real model.

    Sentence(start=0, words=("●", "▪")).text -> anything but "", "-", "•".
    """
    text = Sentence(start=0, words=("●", "▪")).text

    assert text not in _MEASURED_SILENT_IN_KOKORO, (
        f"fallback {text!r} is a token measured silent in the real model -- "
        "allocate() would raise ValueError on its 0.0s duration"
    )


def test_words_and_stop_are_unaffected_by_bullet_stripping():
    """Stripping bullets from .text must not shift what .words/.stop index
    into the page -- the timeline positions words by count, not by glyph.

    Sentence(start=3, words=("●Set", "up", "●", "the", "●cluster")).stop -> 8.
    """
    words = ("●Set", "up", "●", "the", "●cluster")
    sentence = Sentence(start=3, words=words)

    assert sentence.words == words
    assert len(sentence.words) == 5
    assert sentence.stop == 8


@given(
    st.lists(
        st.text(alphabet="abcXYZ019-●•▪", min_size=0, max_size=6),
        min_size=1,
        max_size=15,
    )
)
def test_spoken_text_never_contains_a_bullet_glyph(words):
    """For any words a unit might hold, the synthesiser never sees ● • ▪,
    and .words -- what the page displays and the timeline indexes by -- is
    untouched."""
    sentence = Sentence(start=0, words=tuple(words))

    assert not any(glyph in sentence.text for glyph in _BULLET_GLYPHS)
    assert sentence.words == tuple(words)
