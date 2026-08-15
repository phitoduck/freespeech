"""BDD bindings for the ``@property`` scenarios of features/karaoke.feature.

Only the ``@property`` scenarios are bound here, via explicit ``scenario()``
decorators (not ``scenarios()``) — the ``@docs`` scenarios in that file are
implemented elsewhere and must stay unbound in this module.

Most ``@then`` steps draw many examples from their ``@given`` strategy via
``_for_each_page``, which does the "build a timeline, skip allocate's
ValueError outcome" boilerplate once so each step is just its assertion, e.g.
``_for_each_page(strategy, op, lambda spans, words, duration, data:
len(spans) == len(words))`` runs that check over hundreds of generated pages.
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
from hypothesis import given as for_all
from hypothesis import settings
from pytest_bdd import given, scenario, then, when
from reader.domain.sentences import MAX_UNIT_WORDS, split_sentences
from reader.domain.timeline import allocate, speech_cost, word_at

from tests.properties.strategies import (
    durations,
    long_unpunctuated_word_lists,
    number_pairs_by_digit_count,
    pages_with_duration,
    word_pairs_by_cost,
)

# Rounding tolerance for span boundary comparisons: spans are built by summing
# up to 60 per-word float shares of a duration up to 600s, so a few ULPs of
# drift is expected and not a bug.
_TOL = 1e-6

# The spec's own ceiling on a synthesis unit, independent of whatever
# MAX_UNIT_WORDS the splitter happens to declare. Measured on real PDFs
# (see karaoke.feature): units over 30 words are where timing drift became
# audible, so 30 is a design requirement, not an implementation detail --
# raising MAX_UNIT_WORDS must not be able to satisfy this assertion.
_SPEC_MAX_UNIT_WORDS = 30

# page_duration_strategy now spans allocate's degenerate regime too (see
# strategies.any_positive_duration) — a narrow ~60-value window that
# Hypothesis's default 100 examples only lands in about half the time. Enough
# examples to make that a near-certainty, still well under a second.
_DEGENERATE_EXAMPLES = 500


def _instants(low: float, high: float) -> st.SearchStrategy[float]:
    """A moment inside the audio, for asking which word is being spoken then.

    >>> _instants(0.0, 2.0).example() <= 2.0
    True
    """
    return st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False)


def _for_each_page(strategy, op, assertion, *, examples=_DEGENERATE_EXAMPLES):
    """Assert something about every generated page's spans, skipping allocate's ValueError outcome.

    ``data`` is a Hypothesis ``st.data()`` draw source, for assertions that need to draw
    more values (e.g. an instant) once ``duration`` is known; assertions that don't need
    it just ignore the parameter.

    >>> _for_each_page(pages_with_duration(), allocate,
    ...                 lambda spans, words, duration, data: len(spans) == len(words))
    """

    @settings(max_examples=examples)
    @for_all(strategy, st.data())
    def check(page, data):
        words, duration = page
        try:
            spans = op(words, duration)
        except ValueError:
            return
        assert assertion(spans, words, duration, data)

    check()


def _for_each_units_page(strategy, op, assertion, *, examples=_DEGENERATE_EXAMPLES):
    """Like ``_for_each_page``, but for ``split_sentences``: one argument (words,
    no duration) and no ``ValueError`` outcome to skip.

    >>> _for_each_units_page(long_unpunctuated_word_lists(), split_sentences,
    ...                       lambda units, words: len(units) >= 1)
    """

    @settings(max_examples=examples)
    @for_all(strategy)
    def check(words):
        units = op(words)
        assert assertion(units, words)

    check()


@scenario("karaoke.feature", "No synthesis unit is long enough for timing to drift")
def test_no_synthesis_unit_is_long_enough_for_timing_to_drift():
    pass


@scenario("karaoke.feature", "Any page's timeline covers its audio exactly once")
def test_timeline_covers_its_audio_exactly_once():
    pass


@scenario("karaoke.feature", "Any page's timeline has one span per word")
def test_timeline_has_one_span_per_word():
    pass


@scenario("karaoke.feature", "Every word is given a share of the audio")
def test_every_word_is_given_a_share_of_the_audio():
    pass


@scenario("karaoke.feature", "A number is given time in proportion to how long it takes to say")
def test_a_number_is_given_time_in_proportion_to_how_long_it_takes_to_say():
    pass


@scenario("karaoke.feature", "Longer words are never given less time than shorter ones")
def test_longer_words_are_never_given_less_time_than_shorter_ones():
    pass


@scenario("karaoke.feature", "Looking up the spoken word is defined at every instant")
def test_word_lookup_is_defined_at_every_instant():
    pass


# ---------------------------------------------------------------- given ----


@given("any page of words and any audio duration", target_fixture="page_duration_strategy")
def _page_duration_strategy():
    return pages_with_duration()


@given(
    "any two words where the first takes longer to say than the second",
    target_fixture="word_pair_strategy",
)
def _word_pair_strategy():
    return word_pairs_by_cost()


@given("any page of words, punctuated or not", target_fixture="unpunctuated_page_strategy")
def _unpunctuated_page_strategy():
    return long_unpunctuated_word_lists()


@given(
    "any two numbers where the first has more digits than the second",
    target_fixture="number_pair_strategy",
)
def _number_pair_strategy():
    return number_pairs_by_digit_count()


# ----------------------------------------------------------------- when ----


@when("a timeline is built for them", target_fixture="build_timeline_op")
def _build_timeline_op():
    return lambda words, duration: allocate(words, duration)


@when("it is split into synthesis units", target_fixture="split_units_op")
def _split_units_op():
    return lambda words: split_sentences(words)


@when("a timeline is built for a page containing both", target_fixture="build_pair_timeline_op")
def _build_pair_timeline_op():
    return lambda w1, w2, duration: allocate([w1, w2], duration)


# ----------------------------------------------------------------- then ----


@then("the spans are in ascending order")
def _spans_are_ascending(page_duration_strategy, build_timeline_op):
    def ascending(spans, words, duration, data):
        starts = [span.start for span in spans]
        return starts == sorted(starts)

    _for_each_page(page_duration_strategy, build_timeline_op, ascending)


@then("no two spans overlap")
def _no_two_spans_overlap(page_duration_strategy, build_timeline_op):
    def no_overlap(spans, words, duration, data):
        pairs = zip(spans, spans[1:], strict=False)
        return all(earlier.end <= later.start + _TOL for earlier, later in pairs)

    _for_each_page(page_duration_strategy, build_timeline_op, no_overlap)


@then("there are no gaps between spans")
def _no_gaps_between_spans(page_duration_strategy, build_timeline_op):
    def no_gaps(spans, words, duration, data):
        return all(
            math.isclose(earlier.end, later.start, abs_tol=_TOL)
            for earlier, later in zip(spans, spans[1:], strict=False)
        )

    _for_each_page(page_duration_strategy, build_timeline_op, no_gaps)


@then("the first span starts at 0.0")
def _first_span_starts_at_zero(page_duration_strategy, build_timeline_op):
    _for_each_page(
        page_duration_strategy,
        build_timeline_op,
        lambda spans, words, duration, data: math.isclose(spans[0].start, 0.0, abs_tol=_TOL),
    )


@then("the last span ends at the audio duration")
def _last_span_ends_at_the_audio_duration(page_duration_strategy, build_timeline_op):
    _for_each_page(
        page_duration_strategy,
        build_timeline_op,
        lambda spans, words, duration, data: math.isclose(spans[-1].end, duration, abs_tol=_TOL),
    )


@then("there is exactly one span per word, in the same order")
def _one_span_per_word_in_order(page_duration_strategy, build_timeline_op):
    def one_per_word(spans, words, duration, data):
        return len(spans) == len(words) and [s.word_index for s in spans] == list(range(len(words)))

    _for_each_page(page_duration_strategy, build_timeline_op, one_per_word)


@then("every span has a positive duration")
def _every_span_has_a_positive_duration(page_duration_strategy, build_timeline_op):
    _for_each_page(
        page_duration_strategy,
        build_timeline_op,
        lambda spans, words, duration, data: all(span.duration > 0 for span in spans),
    )


@then("the first is allotted at least as much time as the second")
def _more_digits_costs_at_least_as_much(number_pair_strategy):
    @for_all(number_pair_strategy)
    def check(pair):
        longer, shorter = pair
        assert speech_cost(longer) >= speech_cost(shorter)

    check()


@then("a number is never quicker to say than a single letter")
def _number_never_quicker_than_a_letter(number_pair_strategy):
    # A single digit costs a shade more than a single letter (DIGIT_COST 0.65
    # vs "a" at 0.55 + 0.08), so this has real headroom and _TOL is belt and
    # braces. It is kept deliberately: an earlier DIGIT_COST of exactly 0.63
    # made the two sides equal in arithmetic but a float ULP apart in fact,
    # because one is pre-summed and the other accumulates. If the constant is
    # ever tuned back toward a letter's cost, this tolerance is what stops a
    # true statement failing on the sixteenth decimal place.
    @for_all(number_pair_strategy)
    def check(pair):
        longer, shorter = pair
        assert speech_cost(longer) >= speech_cost("a") - _TOL
        assert speech_cost(shorter) >= speech_cost("a") - _TOL

    check()


@then("the first word's span is at least as long as the second's")
def _first_word_span_at_least_as_long_as_second(word_pair_strategy, build_pair_timeline_op):
    @for_all(st.tuples(word_pair_strategy, durations))
    def check(example):
        (w1, w2), duration = example
        spans = build_pair_timeline_op(w1, w2, duration)
        assert spans[0].duration >= spans[1].duration - _TOL

    check()


@then("looking up any instant inside the audio returns exactly one word")
def _lookup_returns_exactly_one_word(page_duration_strategy, build_timeline_op):
    def one_word(spans, words, duration, data):
        index = word_at(spans, data.draw(_instants(0.0, duration)))
        return index is not None and 0 <= index < len(words)

    _for_each_page(page_duration_strategy, build_timeline_op, one_word)


@then("the word returned never moves backwards as the instant advances")
def _lookup_is_monotonic(page_duration_strategy, build_timeline_op):
    def monotonic(spans, words, duration, data):
        t1 = data.draw(_instants(0.0, duration))
        t2 = data.draw(_instants(t1, duration))
        index1 = word_at(spans, t1)
        index2 = word_at(spans, t2)
        return index1 is not None and index2 is not None and index2 >= index1

    _for_each_page(page_duration_strategy, build_timeline_op, monotonic)


@then("no unit is longer than 30 words")
def _no_unit_longer_than_spec_limit(unpunctuated_page_strategy, split_units_op):
    _for_each_units_page(
        unpunctuated_page_strategy,
        split_units_op,
        lambda units, words: all(len(unit.words) <= _SPEC_MAX_UNIT_WORDS for unit in units),
    )


@then("no unit is longer than the limit the splitter declares")
def _no_unit_longer_than_declared_limit(unpunctuated_page_strategy, split_units_op):
    _for_each_units_page(
        unpunctuated_page_strategy,
        split_units_op,
        lambda units, words: all(len(unit.words) <= MAX_UNIT_WORDS for unit in units),
    )


@then("the units together still contain every word, in order")
def _units_contain_every_word_in_order(unpunctuated_page_strategy, split_units_op):
    def covers(units, words):
        reconstructed = [word for unit in units for word in unit.words]
        if reconstructed != list(words):
            return False
        # build_timeline indexes back into the input page by start/stop, so a
        # unit whose slice doesn't match its own words would corrupt timing.
        return all(words[unit.start : unit.stop] == list(unit.words) for unit in units)

    _for_each_units_page(unpunctuated_page_strategy, split_units_op, covers)
