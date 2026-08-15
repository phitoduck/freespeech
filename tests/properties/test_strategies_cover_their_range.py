"""Assert the suite's strategies actually reach the ranges they declare.

Four real defects hid behind green property tests because a strategy claimed
a range it never drew from. Worst case: ``word_lists`` declared 1..60 via
plain ``st.lists(..., max_size=60)``, which measured median 6 and reached 60
in 0 of 15,000 draws -- so a 262-word production synthesis unit, and
``split_sentences`` on bullet lists and CVs, were never exercised. A
docstring can claim "1..300" forever without anyone noticing draws top out
at 19; these tests check the *distribution*, not just the declared bound, so
a collapse back to a short/tame regime fails loudly here.
"""

from __future__ import annotations

import re

from hypothesis import HealthCheck, given, settings
from reader.domain.timeline import allocate

from tests.properties.strategies import (
    long_unpunctuated_word_lists,
    number_pairs_by_digit_count,
    pages_with_duration,
    word_lists,
)

_SAMPLES = 800

# Above the largest degenerate duration (~3e-322) and below the smallest
# ordinary one (0.05): anything under this is degenerate, full stop.
_DEGENERATE_CUTOFF = 1e-300


def _collect(strategy, examples=_SAMPLES):
    """Draw ``examples`` values via ``@given`` + a closure -- strategies
    aren't iterables, so this is the only way to sample many at once.

    >>> len(_collect(word_lists()))
    800
    """
    drawn = []

    @settings(max_examples=examples, deadline=None, suppress_health_check=list(HealthCheck))
    @given(strategy)
    def _draw(value):
        drawn.append(value)

    _draw()
    return drawn


def test_word_lists_still_reaches_long_lists():
    """Guards against collapsing to st.lists(max_size=60)'s median-6 shape,
    which hit the ceiling 0 times in 15,000 draws (measured here: median 33,
    >=40 in ~37%, asserted below with headroom)."""
    sizes = [len(words) for words in _collect(word_lists())]
    assert sum(1 for n in sizes if n >= 40) / len(sizes) > 0.10
    assert max(sizes) >= 55


def test_long_unpunctuated_word_lists_still_reaches_long_and_unpunctuated():
    """Guards two collapses at once: shrinking lists, and a generator that
    quietly starts punctuating every word -- the exact shape of the 262-word
    bug, since split_sentences only sees long unbroken runs when most words
    carry no terminator at all."""
    lists = _collect(long_unpunctuated_word_lists(), examples=300)
    sizes = [len(w) for w in lists]
    assert sum(1 for n in sizes if n >= 100) / len(sizes) > 0.40
    unpunctuated = [
        sum(1 for w in words if not w.endswith((".", "!", "?"))) / len(words) for words in lists
    ]
    assert sum(unpunctuated) / len(unpunctuated) > 0.70


def test_any_positive_duration_still_produces_degenerate_durations():
    """Measured in situ via pages_with_duration(), not standalone: a one_of
    branch's selection rate shifts with what's drawn alongside it --
    standalone this reads ~2% degenerate, in situ ~40%."""
    pages = _collect(pages_with_duration())
    degenerate = sum(1 for _, d in pages if d < _DEGENERATE_CUTOFF)
    assert degenerate / len(pages) > 0.20


def test_pages_with_duration_still_reaches_the_collision_regime():
    """Guards the JOINT regime allocate's nextafter guard needs: a degenerate
    duration together with a long word list, chaining many boundary
    collisions in a row instead of just one."""
    pages = _collect(pages_with_duration())
    joint = sum(1 for w, d in pages if d < _DEGENERATE_CUTOFF and len(w) >= 40)
    assert joint / len(pages) > 0.03


def test_pages_with_duration_still_lets_allocate_succeed_often_enough():
    """Counter-direction check: if degenerate durations dominated, nearly
    every draw would raise ValueError and the real assertions downstream
    (tests/bdd/test_karaoke_properties.py) would rarely execute."""
    pages = _collect(pages_with_duration())

    def _raises(words, duration) -> bool:
        try:
            allocate(words, duration)
        except ValueError:
            return True
        return False

    raised = sum(1 for w, d in pages if _raises(w, d))
    assert raised / len(pages) < 0.50


def test_number_pairs_by_digit_count_still_reaches_wide_digit_gaps():
    """Guards against the digit-count draw collapsing to adjacent counts only
    (e.g. always 2 vs 1), which would leave the "more digits" property
    exercised only at its easiest, smallest margin."""
    pairs = _collect(number_pairs_by_digit_count())
    gaps = [len(re.findall(r"\d", a)) - len(re.findall(r"\d", b)) for a, b in pairs]
    assert max(gaps) >= 6
    assert sum(1 for g in gaps if g >= 4) / len(gaps) > 0.10
