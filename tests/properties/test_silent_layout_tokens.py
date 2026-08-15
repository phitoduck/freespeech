"""spoken(word) strips bullet glyphs and dot leaders, but other layout tokens
that produce ZERO audio from the real Kokoro model survived untouched -- so
speech_cost billed them a full BASE_COST share of the timeline while the voice
made no sound, and the highlight parked on them.

Measured against KokoroSynthesizer, voice="am_adam":
    '​' (zero-width space) 0.0s   '-' 0.0s   '–' (en dash) 0.0s   '^^' 0.0s

Corpus (2,653 tokens, nine real PDFs): '●​' (a bullet glued to a ZWSP) x39,
bare '​' x14, '-' x22, '–' x7, '^^' x4 -- 86 tokens, 3.2%, each billed 1.00.

>>> from reader.domain.sentences import spoken
>>> spoken("​")
''
"""

from __future__ import annotations

import pytest
from hypothesis import given
from reader.domain.sentences import Sentence, spoken
from reader.domain.timeline import UNSPOKEN_COST, speech_cost

from tests.properties.strategies import words as _real_words

_ZWSP = "​"
_EN_DASH = "–"

# Tokens measured to produce 0.0s of audio from the real KokoroSynthesizer
# (voice="am_adam"); allocate() raises ValueError on a zero-duration unit, so
# a Sentence.text fallback landing on any of these is a real 500 -- the same
# hazard the sibling suite's _MEASURED_SILENT_IN_KOKORO pins for "-" and "•".
_MEASURED_SILENT = frozenset({"", "-", _EN_DASH, "^^", _ZWSP})

# Measured audible from the real model (voice="am_adam"): 🎉 1.29s, & 0.74s,
# + 0.89s, / 0.91s, = 0.93s, → 0.95s, ~ 0.80s, +$ 0.93s. None of them has a
# letter or a digit, so they are what stops the fix being "strip any token
# with neither".
_VOICED_TOKENS = ["\U0001f389", "&", "+", "/", "=", "→", "~", "+$"]


@pytest.mark.parametrize("token", [_ZWSP, f"●{_ZWSP}"])
def test_a_zero_width_space_token_is_priced_as_unspoken(token):
    """A zero-width space is invisible whitespace, not content -- bare or
    glued to a stripped bullet, it must vanish from the spoken form and be
    billed UNSPOKEN_COST, not a full BASE_COST share.

    spoken('​') -> ''
    spoken('●​') -> ''
    """
    assert spoken(token) == ""
    assert speech_cost(token) == UNSPOKEN_COST


@pytest.mark.parametrize("token", ["-", _EN_DASH, "^^"])
def test_a_token_that_is_entirely_dashes_or_carets_is_priced_as_unspoken(token):
    """'-', '–' and '^^' each measured 0.0s of audio (voice="am_adam"), yet
    were billed a full BASE_COST share of the timeline before this fix.

    spoken('-') -> ''
    """
    assert spoken(token) == ""
    assert speech_cost(token) == UNSPOKEN_COST


# Deleted: a cost-only check that 'well-known'/'-5' keep their normal cost. A
# '-' scores no letter, vowel or digit, so over-stripping dashes leaves the cost
# identical -- confirmed by mutation. The regression is caught by text, not
# cost: test_sentence_text.py::test_hyphen_is_not_a_bullet_and_survives was the
# only test in the suite that went red under it.


def test_a_zwsp_on_a_real_word_survives_as_the_word_in_sentence_text():
    """The word itself must still reach the synthesiser -- only the invisible
    character is dropped.

    Sentence(start=0, words=('Engineer​',)).text -> 'Engineer'.
    """
    assert Sentence(start=0, words=(f"Engineer{_ZWSP}",)).text == "Engineer"


@pytest.mark.parametrize("token", _VOICED_TOKENS)
def test_a_voiced_symbol_token_keeps_a_full_share_of_the_timeline(token):
    """Every _VOICED_TOKENS entry is measured audible, so the fix must not
    reach them. This test exists to make the over-broad version -- drop any
    token with no letters or digits -- fail.

    speech_cost('&') -> > UNSPOKEN_COST
    """
    assert speech_cost(token) > UNSPOKEN_COST


def test_a_unit_of_only_a_silent_layout_token_does_not_fall_back_to_a_silent_token():
    """Non-emptiness is not proof of audibility (the real model produces 0.0s
    for several non-empty, glyph-free tokens too), so a unit of nothing but a
    silent token must not let Sentence.text's fallback land on another token
    also measured silent -- that would still crash allocate() on a 0.0s
    duration. One token is enough: the fallback is a single literal, reached
    identically however .text came out empty.

    Sentence(start=0, words=('​',)).text -> not in {'', '-', '–', '^^', '​'}.
    """
    text = Sentence(start=0, words=(_ZWSP,)).text

    assert text not in _MEASURED_SILENT, (
        f"fallback {text!r} is a token measured silent in the real model -- "
        "allocate() would raise ValueError on its 0.0s duration"
    )


@given(prefix=_real_words, suffix=_real_words)
def test_a_zwsp_splitting_a_vowel_pair_never_changes_a_words_cost(prefix, suffix):
    """Generalises the fixed leading/mid/trailing cases above: a ZWSP dropped
    between two vowels ('a​a') must not be counted as a syllable break,
    for any real prefix/suffix around it. A fixed example ('Engineer​')
    can only probe the boundary it names; wedging the ZWSP inside a vowel
    pair is the one placement guaranteed to move the syllable count if it is
    not stripped first, so this is deterministic rather than depending on
    Hypothesis happening to draw adjacent vowels on its own.
    """
    word = f"{prefix}aa{suffix}"
    decorated = f"{prefix}a{_ZWSP}a{suffix}"

    assert speech_cost(decorated) == speech_cost(word)
