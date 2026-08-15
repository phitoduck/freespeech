"""build_timeline must price each word by what is actually spoken for it
(sentences.spoken), not by the raw token. Before this fix a standalone dot
leader or bullet -- EMPTY spoken form -- still earned a full BASE_COST-sized
(or larger) slice of the audio, so the highlight lagged the voice by however
long that slice lasted.

Contract for a silent-but-visible token's cost: strictly less than
BASE_COST, the floor speech_cost() adds to every word unconditionally. Any
token with a real spoken form costs strictly more than that floor (it adds
at least one syllable, letter or digit's worth of cost on top), so "below
BASE_COST" is exactly "must not receive a full BASE_COST-sized slice" in
this module's own terms, not a number invented for this test.

>>> from reader.domain.timeline import allocate
>>> spans = allocate(["Introduction", "." * 10, "7"], duration=7.21)
>>> round(spans[1].duration, 2)  # the silent dots, once priced by spoken form
0.06
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
from hypothesis import given
from reader.domain.sentences import Sentence
from reader.domain.timeline import BASE_COST, build_timeline, speech_cost

from tests.properties.strategies import durations, words

_TOL = 1e-9

# How far below BASE_COST an implied cost must land to count as "not a
# BASE_COST-sized slice". A bare bullet's raw speech_cost() is exactly
# BASE_COST (no letters/digits/syllables to add), so allocate()'s float
# division can hand back an implied cost a few ULPs under 1.0 (measured:
# 0.9999999999999998) with NO fix applied at all -- `< BASE_COST` alone
# would pass on that noise. 1e-6 is far above that noise floor (~1e-16 at
# this magnitude) and far below any real fix's expected margin (the whole
# point is the silent token's cost should be MUCH smaller, not one part in
# a million smaller).
_MEANINGFUL_MARGIN = 1e-6


def _implied_cost(spans, index: int, reference_index: int, reference_cost: float) -> float:
    """Back out the cost allocate() must have used for spans[index], using a
    neighbour whose cost is known and unaffected by the bug (a plain word
    has no bullet/leader to strip, so its cost is speech_cost() of itself
    either way). allocate() splits duration in exact proportion to cost, so
    this recovers the cost without needing a public hook into the fix.

    >>> from reader.domain.timeline import allocate
    >>> spans = allocate(["a", "bb"], 3.0)
    >>> round(_implied_cost(spans, 1, 0, speech_cost("a")), 2)  # == speech_cost("bb")
    1.16
    """
    return reference_cost * spans[index].duration / spans[reference_index].duration


def test_a_standalone_leader_does_not_get_a_base_cost_sized_share():
    """The exact token shapes and duration measured on a real table-of-
    contents unit (see .humanlayer task notes): 'Introduction' (spoken
    unchanged), a standalone 10-dot leader (spoken form ''), '7' (spoken
    unchanged), totalling 7.21s of audio.

    build_timeline([Sentence(start=0, words=("Introduction", "." * 10, "7"))],
    [7.21]) -> the dots span's implied cost is < BASE_COST (1.0).
    """
    sentence = Sentence(start=0, words=("Introduction", "." * 10, "7"))
    spans = build_timeline([sentence], [7.21])

    implied_dots_cost = _implied_cost(spans, 1, 0, speech_cost("Introduction"))

    assert implied_dots_cost < BASE_COST - _MEANINGFUL_MARGIN, (
        f"leader token priced at {implied_dots_cost:.3f}, not below the "
        f"BASE_COST floor ({BASE_COST}) every spoken word already clears"
    )
    # contract #2: still visible, still gets a positive sliver of time
    assert spans[1].duration > 0
    # contract #4: unaffected -- one span per word, in order, contiguous
    assert len(spans) == 3
    assert [s.word_index for s in spans] == [0, 1, 2]
    assert spans[0].end == spans[1].start
    assert spans[1].end == spans[2].start


def test_a_standalone_bullet_does_not_get_a_base_cost_sized_share():
    """A bare bullet glyph (its own token, not glued to a word) has spoken
    form '' just like a leader -- same defect, different glyph. Priced on the
    raw token it costs exactly BASE_COST (no letters, digits or syllables),
    which is already the violation: a token that says nothing must cost LESS
    than one that merely says nothing extra, i.e. strictly under the floor.

    build_timeline([Sentence(start=0, words=("cat", "●"))], [5.0]) -> the
    bullet span's implied cost is < BASE_COST (1.0).
    """
    sentence = Sentence(start=0, words=("cat", "●"))
    spans = build_timeline([sentence], [5.0])

    implied_bullet_cost = _implied_cost(spans, 1, 0, speech_cost("cat"))

    assert implied_bullet_cost < BASE_COST - _MEANINGFUL_MARGIN, (
        f"bullet token priced at {implied_bullet_cost:.3f}, not below the "
        f"BASE_COST floor ({BASE_COST})"
    )
    assert spans[1].duration > 0


def test_a_trailing_leader_does_not_earn_a_sentence_ending_pause():
    """'Wait....' ends in '.', so pricing the raw token scores it as if a
    sentence just ended (+SENTENCE_PAUSE), even though its spoken form is
    'Wait' -- no terminal punctuation at all once the leader is stripped.

    build_timeline([Sentence(start=0, words=("Wait....", "friend"))], [10.0])
    -> the 'Wait....' span's implied cost equals speech_cost('Wait') (1.87).
    Before this fix it was 2.77 -- the same 1.87 plus a SENTENCE_PAUSE earned
    for a full stop nobody hears.
    """
    sentence = Sentence(start=0, words=("Wait....", "friend"))
    spans = build_timeline([sentence], [10.0])

    implied_wait_cost = _implied_cost(spans, 0, 1, speech_cost("friend"))

    assert math.isclose(implied_wait_cost, speech_cost("Wait"), abs_tol=_TOL), (
        f"'Wait....' priced at {implied_wait_cost:.3f}, expected "
        f"speech_cost('Wait') = {speech_cost('Wait'):.3f} (no sentence pause)"
    )


# ------------------------------------------------------------- property ----

_SILENT_TOKENS = st.one_of(
    st.text(alphabet=".", min_size=4, max_size=50),  # a dot leader, standalone
    st.sampled_from(["●", "▪", "•"]),  # ● ▪ •, standalone
)
"""Tokens whose spoken form (Sentence.text) is empty on their own -- the
shape field-reported on a real user PDF (see task notes), not present in
the 2,653-token corpus this project's own strategies are calibrated
against. Kept separate from strategies.py for that reason."""


@given(plain=words, silent=_SILENT_TOKENS, duration=durations)
def test_any_standalone_silent_token_costs_less_than_base_cost(plain, silent, duration):
    """For any plain word (alphanumeric, real spoken form) paired with any
    standalone silent token (bare leader or bullet, empty spoken form), the
    silent token's implied cost never reaches the BASE_COST floor -- while
    the plain word's cost is untouched by the fix, since it has nothing to
    strip.
    """
    sentence = Sentence(start=0, words=(plain, silent))
    try:
        spans = build_timeline([sentence], [duration])
    except ValueError:
        return  # duration too short to give 2 words distinct spans -- not what this checks

    implied_silent_cost = _implied_cost(spans, 1, 0, speech_cost(plain))

    assert implied_silent_cost < BASE_COST - _MEANINGFUL_MARGIN
    assert spans[1].duration > 0
