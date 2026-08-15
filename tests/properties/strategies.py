"""Hypothesis strategies shared by the property suites — the "Examples table
with infinitely many rows" behind the ``@property`` scenarios in ``features/``.

word_lists().example()  # -> ['Hello,', 'world9']
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
from hypothesis import assume
from reader.domain.timeline import speech_cost

# Printable, non-whitespace tokens: whatever survives PDF word extraction.
# Kept to Latin letters, digits and common punctuation so the generated PDFs in
# the extraction round-trip render with the built-in fonts.
_WORD_CHARS = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)

words = st.text(alphabet=_WORD_CHARS, min_size=1, max_size=14)
"""A single bare word, no punctuation."""

punctuated_words = st.builds(
    lambda body, tail: body + tail,
    words,
    st.sampled_from(["", "", "", ",", ".", "!", "?", ";", ":"]),
)
"""A word that may carry trailing punctuation, so pause weighting is exercised."""

@st.composite
def word_lists(draw) -> list[str]:
    """A page's worth of words.

    Size is drawn explicitly over 1..60 rather than via plain
    ``st.lists(..., max_size=60)``: that default skews heavily towards short
    lists (measured over 15,000 draws: median 6, p90 15, p99 29, and 0 of
    15,000 ever reached the declared ceiling of 60), starving the collision
    regime ``allocate``'s ``nextafter`` guard was calibrated against -- the
    same trap already fixed once for ``long_unpunctuated_word_lists`` below.

    >>> word_lists().example()  # -> ['Hello,', 'world9']
    """
    size = draw(st.integers(min_value=1, max_value=60))
    return [draw(punctuated_words) for _ in range(size)]

durations = st.floats(
    min_value=0.05,
    max_value=600.0,
    allow_nan=False,
    allow_infinity=False,
)
"""A plausible audio length in seconds — "nobody synthesises a ten-minute
sentence" at the top, comfortably clear of float weirdness at the bottom.

For properties about *typical* durations only (e.g. comparing two words'
relative timing); ``any_positive_duration`` below covers allocate's full
contract, degenerate regime included.
"""

def _nth_positive_double(n: int) -> float:
    """Walk up from 0.0 to the n-th smallest representable positive double.

    >>> _nth_positive_double(1)
    5e-324
    """
    value = 0.0
    for _ in range(n):
        value = math.nextafter(value, math.inf)
    return value


_DEGENERATE_DURATIONS = st.integers(min_value=1, max_value=60).map(_nth_positive_double)
"""The bottom 60 representable positive doubles: 5e-324 up to ~2.96e-322.

``allocate``'s boundary arithmetic (``duration * running_cost / total_cost``)
is relative, so it stays exact down to the point where multiplying by a
fraction underflows straight to 0.0. Walking ``math.nextafter`` from 0.0 while
re-running ``allocate`` against varied word lists found that collisions stop
for good at exactly the 60th double — measured, not guessed, and kept exactly
that tight rather than padded, since padding a strategy this narrow just
dilutes how often a few hundred examples actually hit every value in it.
"""

any_positive_duration = st.one_of(durations, _DEGENERATE_DURATIONS)
"""Any positive, finite duration ``allocate`` can legally be called with.

Use this (via ``pages_with_duration``) for properties asserting allocate's
full contract — contiguous, ascending, strictly positive spans, or
``ValueError`` and no third outcome; use ``durations`` where a property
assumes success and is about something else.
"""


_BULLET_PREFIX = st.sampled_from(["", "", "", "", "", "", "", "", "", "", "●", "•", "-"])
"""Mostly nothing; occasionally a bullet-list marker glued onto the next word,
exactly how PDF text extraction hands back a bulleted line (no space between
the glyph and the word that follows it)."""

_RARE_TERMINATOR = st.sampled_from([""] * 24 + [".", "!", "?"])
"""Trailing punctuation on roughly 1 in 25 words -- rare enough that runs of
dozens of consecutive words with no sentence-ending punctuation are the norm,
not the exception. Real unpunctuated documents (bullet lists, headings, table
cells) are exactly this: long stretches with no terminator at all."""


@st.composite
def _unpunctuated_word(draw) -> str:
    """A word that only rarely ends a sentence, sometimes bullet-prefixed.

    >>> _unpunctuated_word().example()  # -> '●Weekly'
    """
    return draw(_BULLET_PREFIX) + draw(words) + draw(_RARE_TERMINATOR)


@st.composite
def long_unpunctuated_word_lists(draw) -> list[str]:
    """A page's worth of words dominated by long runs with no terminal
    punctuation at all -- the regime real PDFs produce for bullet lists,
    headings, table cells and CVs, where ``word_lists`` above (mostly-
    punctuated) rarely reaches.

    Size is drawn explicitly and roughly uniformly over 1..300 rather than
    via plain ``st.lists(..., max_size=300)``: that default skews heavily
    towards short lists (measured: 300 examples of ``st.lists(max_size=300)``
    topped out at 19 words, none over 30), which would make this strategy --
    and the property it feeds -- vacuous.

    >>> long_unpunctuated_word_lists().example()
    ... # -> ['●Weekly', '2hr', 'class', 'QA', 'on', 'Wednesdays', '●Meet', 'friendly', ...]
    """
    size = draw(st.integers(min_value=1, max_value=300))
    return [draw(_unpunctuated_word()) for _ in range(size)]


@st.composite
def pages_with_duration(draw) -> tuple[list[str], float]:
    """A page of words and an audio duration for it, drawn together since a
    static Examples table can't express "a duration that suits these words".

    pages_with_duration().example()  # -> (['Hi!', 'there'], 12.4)
    """
    return draw(word_lists()), draw(any_positive_duration)


@st.composite
def word_pairs_by_cost(draw) -> tuple[str, str]:
    """Two words, ordered so the first never costs less to say than the second.

    word_pairs_by_cost().example()  # -> ('Hello!', 'Hi')
    """
    a = draw(punctuated_words)
    b = draw(punctuated_words)
    assume(speech_cost(a) != speech_cost(b))  # a tie leaves nothing to assert about "longer"
    if speech_cost(a) < speech_cost(b):
        a, b = b, a
    return a, b


def _digits(draw, n: int) -> str:
    """A string of exactly n random digit characters.

    >>> len(_digits(lambda strategy: strategy.example(), 4))
    4
    """
    return "".join(str(draw(st.integers(min_value=0, max_value=9))) for _ in range(n))


@st.composite
def number_pairs_by_digit_count(draw) -> tuple[str, str]:
    """Two digit strings, the first with strictly more digits than the second.

    Digit counts are drawn explicitly via ``st.integers`` (1..6 for the shorter
    token, 1..7 more than that for the longer one) rather than left to a
    collection strategy's default sizing, so the gap between them actually
    spans small (2 vs 1 digit) to large (13 vs 1 digit) -- see
    ``test_strategies_cover_their_range.py``.

    Realistic formatting ($4,500 / 1,250,000 / 2024-08-15 / 9:30) was tried
    here and dropped: none of those separator characters match speech_cost's
    letter or digit regexes, and none of them land as trailing punctuation
    either, so "$4,500" costs exactly what "4500" costs. Dressing the digits
    up exercised nothing bare digits didn't already cover.

    >>> number_pairs_by_digit_count().example()  # -> ('1234567', '12')
    """
    shorter_digits = draw(st.integers(min_value=1, max_value=6))
    longer_digits = draw(st.integers(min_value=shorter_digits + 1, max_value=shorter_digits + 7))
    return _digits(draw, longer_digits), _digits(draw, shorter_digits)
