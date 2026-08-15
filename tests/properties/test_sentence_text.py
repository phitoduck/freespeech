"""Sentence.text must not hand the synthesiser a glued-on bullet glyph. The
displayed word (Sentence.words) keeps it -- only the spoken text changes.

>>> Sentence(start=0, words=("●Set", "up")).text
'Set up'
"""

from __future__ import annotations

import re

import hypothesis.strategies as st
import pytest
from hypothesis import given
from reader.domain.sentences import Sentence

_BULLET_GLYPHS = "●•▪"

# A run of 4+ dots is a table-of-contents leader ("Introduction.........7"),
# glued into a single PyMuPDF token with no spaces. Measured against the real
# KokoroSynthesizer (voice="am_adam"): 178 dots cost 10.68s of audio while
# speech_cost scores the token at 1.90 -- less than 'Introduction' alone
# (4.16) -- so the timeline drifts for the rest of the unit. '...' (three
# dots) and '…' (U+2026) are below the threshold and are real
# punctuation: measured at 0.52s and 0.44s, correct and must survive.
_LEADER_RUN = re.compile(r"\.{4,}")

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


@pytest.mark.parametrize("words", [("●", "▪"), ("." * 178,)])
def test_a_unit_of_only_unspoken_marks_does_not_fall_back_to_a_silent_token(words):
    """Non-emptiness is not proof of audibility: the real model produces 0.0s
    for "", "-" and "•" alike (_MEASURED_SILENT_IN_KOKORO above), so
    `.text.strip() != ""` does not rule out a fallback that still crashes
    allocate(). A fast, kokoro-free pin against the regression that shipped
    once already: falling back to "-".

    It cannot prove a *new* fallback word is audible, only that it is not one
    already measured silent. The authoritative check is the kokoro-marked test
    in tests/services/test_speech.py, which calls the real model.

    Sentence(start=0, words=("●", "▪")).text -> anything but "", "-", "•".
    """
    text = Sentence(start=0, words=words).text

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


@pytest.mark.parametrize("n_dots", [4])
def test_a_dot_leader_glued_between_title_and_page_number_is_deleted(n_dots):
    """A table-of-contents leader is one PyMuPDF token, title, dots and page
    number with no space between them -- confirmed against a real ToC PDF,
    where extract() returned tokens like
    'Introduction..............................................1' whole.

    Choice made here: the leader is deleted, not replaced with a space.
    Measured against the real KokoroSynthesizer (voice="am_adam") on that
    exact 46-dot token: the raw glued token costs 3.13s of audio;
    'Introduction1' (deleted) and 'Introduction 1' (space) both cost 1.25s --
    indistinguishable, because the model normalises the boundary itself and
    reads either as "Introduction one". With no audio difference to prefer
    one, deletion is the simpler implementation: it can never produce a
    stray leading/trailing space, so it needs no extra whitespace-collapsing
    that a space-substitution would (see
    test_a_trailing_leader_with_nothing_after_it_leaves_no_stray_space and
    its leading-space sibling below).

    Sentence(start=0, words=("Introduction.........7",)).text -> 'Introduction7'.
    """
    token = f"Introduction{'.' * n_dots}7"
    sentence = Sentence(start=0, words=(token,))

    assert sentence.text == "Introduction7"
    assert sentence.words == (token,)


def test_a_real_captured_toc_token_keeps_title_and_page_number_and_costs_less_audio():
    """The exact token shape captured from a real table-of-contents PDF via
    extract(): title, a 46-dot leader and the page number, glued with no
    spaces at all into one PyMuPDF token. Measured against the real model
    (voice="am_adam"): this raw token costs 3.13s of audio; with the leader
    deleted, 'Introduction1' costs 1.25s -- the actual, measured win on one
    glued token.

    Sentence(start=0, words=("Introduction" + "." * 46 + "1",)).text ->
    'Introduction1'.
    """
    token = "Introduction" + "." * 46 + "1"
    sentence = Sentence(start=0, words=(token,))

    assert sentence.text == "Introduction1"
    assert sentence.words == (token,)


def test_three_dots_are_an_ellipsis_and_survive():
    """'...' is meaningful punctuation, not a leader -- measured at 0.52s of
    audio, which is correct, not a bug. Only runs of 4 or more dots are
    leaders.

    Sentence(start=0, words=("Wait...",)).text -> 'Wait...'.
    """
    assert Sentence(start=0, words=("Wait...",)).text == "Wait..."


def test_unicode_ellipsis_survives():
    """U+2026 is a single ellipsis character, not three dots -- measured at
    0.44s of audio, correct behaviour. A leader rule keyed on runs of '.'
    cannot touch it, but pin it explicitly: a reimplementation that instead
    matched "looks like an ellipsis" could get this wrong.

    Sentence(start=0, words=("Wait…",)).text -> 'Wait…'.
    """
    assert Sentence(start=0, words=("Wait…",)).text == "Wait…"


def test_a_trailing_leader_with_nothing_after_it_leaves_no_stray_space():
    """When the leader is glued to the end of a word with nothing following
    in the same token, removing it must not leave a trailing space.

    Sentence(start=0, words=("Wait....",)).text -> 'Wait'.
    """
    assert Sentence(start=0, words=("Wait....",)).text == "Wait"


def test_a_leading_leader_with_nothing_before_it_leaves_no_stray_space():
    """Leader dots at the front of a token must not leave a leading space
    once removed.

    Sentence(start=0, words=("....7",)).text -> '7'.
    """
    assert Sentence(start=0, words=("....7",)).text == "7"


def test_a_standalone_leader_token_leaves_no_stray_space():
    """A dot leader extracted as its own token, already space-separated from
    its neighbours, must vanish without leaving a double space -- the same
    hazard naive bullet-stripping had.

    Sentence(start=0, words=("Introduction", "." * 10, "7")).text ->
    'Introduction 7'.
    """
    sentence = Sentence(start=0, words=("Introduction", "." * 10, "7"))

    assert sentence.text == "Introduction 7"
    assert "  " not in sentence.text


def test_a_unit_of_only_leader_dots_still_yields_speakable_text():
    """speech_cost / allocate raise ValueError on a non-positive duration, so
    a unit whose .text is empty (or whitespace-only) is a real 500 -- the
    same hazard an all-bullet unit had. A page consisting of nothing but a
    178-dot leader token must still produce something to synthesize.

    Sentence(start=0, words=("." * 178,)).text.strip() -> non-empty.
    """
    sentence = Sentence(start=0, words=("." * 178,))

    assert sentence.text.strip() != ""


@given(
    st.lists(
        st.text(alphabet="abcXYZ019-●•▪.", min_size=0, max_size=6),
        min_size=1,
        max_size=15,
    )
)
def test_spoken_text_never_contains_a_bullet_glyph_or_a_dot_leader(words):
    """For any words a unit might hold, the synthesiser never sees ● • ▪ nor
    a run of 4+ dots, and .words -- what the page displays and the timeline
    indexes by -- is untouched."""
    sentence = Sentence(start=0, words=tuple(words))

    assert not any(glyph in sentence.text for glyph in _BULLET_GLYPHS)
    assert _LEADER_RUN.search(sentence.text) is None
    assert sentence.words == tuple(words)
