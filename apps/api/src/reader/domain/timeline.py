"""Estimate when each word is spoken, given only a sentence's total duration.

>>> words = "the cat sat".split()
>>> spans = allocate(words, duration=3.0)
>>> word_at(spans, 1.5)
1
"""

from __future__ import annotations

import math
import re
from bisect import bisect_right
from dataclasses import dataclass

from reader.domain.sentences import Sentence, spoken

_VOWEL_GROUP = re.compile(r"[aeiouy]+", re.IGNORECASE)
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
_DIGITS = re.compile(r"\d")

BASE_COST = 1.0
SYLLABLE_COST = 0.55
LETTER_COST = 0.08
# A digit is read aloud as its own syllable-word ("2024" -> "twenty
# twenty-four", 4 digits ~= 4 syllables), so weight it like the one-letter
# word "a" (a whole syllable plus a letter, SYLLABLE_COST + LETTER_COST =
# 0.63) -- nudged up to 0.65 so float rounding can't make a bare digit
# ("5" -> 1.65) come out cheaper than speech_cost("a") (1.63).
DIGIT_COST = 0.65
CLAUSE_PAUSE = 0.4
SENTENCE_PAUSE = 0.9
# Visible but silent (a bullet, a dot leader) still gets highlighted, so its cost
# must stay above zero -- allocate owes every word a positive span. Well under
# BASE_COST, though: at 1.0 a silent 10-dot leader held the highlight for 1.78s
# of a 7.21s unit.
UNSPOKEN_COST = 0.05


@dataclass(frozen=True, slots=True)
class Span:
    """The stretch of audio during which one word is spoken."""

    word_index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def speech_cost(word: str) -> float:
    """Relative time to say a word, priced on what is actually voiced for it
    (sentences.spoken) rather than on the raw token -- 'Wait....' is said as
    "Wait", so it earns no sentence-ending pause for a full stop nobody hears.

    >>> round(speech_cost("cat"), 2)
    1.79
    >>> round(speech_cost("cat."), 2)
    2.69
    >>> round(speech_cost("2024"), 2)
    3.6
    >>> speech_cost("..........")   # a table-of-contents leader: silent
    0.05
    """
    word = spoken(word)
    if not word:
        return UNSPOKEN_COST
    syllables = len(_VOWEL_GROUP.findall(word))
    letters = len(_LETTERS.findall(word))
    digits = len(_DIGITS.findall(word))
    cost = BASE_COST + SYLLABLE_COST * syllables + LETTER_COST * letters + DIGIT_COST * digits
    trailing = word.rstrip("\"')]}»”’")
    if trailing.endswith((".", "!", "?")):
        cost += SENTENCE_PAUSE
    elif trailing.endswith((",", ";", ":", "—")):
        cost += CLAUSE_PAUSE
    return cost


def allocate(
    words: tuple[str, ...] | list[str],
    duration: float,
    *,
    offset: float = 0.0,
    first_index: int = 0,
) -> list[Span]:
    """Divide duration among words in proportion to speech cost.

    >>> spans = allocate(["a", "bb", "ccc"], 3.0)
    >>> spans[0].start, spans[-1].end
    (0.0, 3.0)
    """
    if not words:
        return []
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError(f"duration must be positive and finite, got {duration!r}")

    costs = [speech_cost(word) for word in words]
    total = math.fsum(costs)
    boundaries = [offset]
    running = 0.0
    for cost in costs[:-1]:
        running += cost
        boundary = offset + duration * (running / total)
        if boundary <= boundaries[-1]:
            boundary = math.nextafter(boundaries[-1], math.inf)
        boundaries.append(boundary)
    boundaries.append(offset + duration)

    if boundaries[-1] <= boundaries[-2]:
        raise ValueError(
            f"duration {duration!r} is too short to give {len(words)} words distinct spans"
        )

    return [
        Span(word_index=first_index + i, start=boundaries[i], end=boundaries[i + 1])
        for i in range(len(words))
    ]


def build_timeline(sentences: list[Sentence], durations: list[float]) -> list[Span]:
    """Lay each sentence's allocation end to end into one page-wide timeline.

    >>> from reader.domain.sentences import split_sentences
    >>> spans = build_timeline(split_sentences(["Hi.", "Bye."]), [1.0, 1.0])
    >>> [(s.start, s.end) for s in spans]
    [(0.0, 1.0), (1.0, 2.0)]
    """
    if len(sentences) != len(durations):
        raise ValueError(f"got {len(sentences)} sentences but {len(durations)} durations")

    spans: list[Span] = []
    offset = 0.0
    for sentence, duration in zip(sentences, durations, strict=True):
        spans.extend(allocate(sentence.words, duration, offset=offset, first_index=sentence.start))
        offset += duration
    return spans


def word_at(spans: list[Span], t: float) -> int | None:
    """Index into spans of the word spoken at instant t, clamped to the timeline.

    >>> spans = allocate(["a", "bb"], 2.0)
    >>> word_at(spans, -1.0), word_at(spans, 10.0)
    (0, 1)
    """
    if not spans:
        return None
    starts = [span.start for span in spans]
    if t <= starts[0]:
        return 0
    if t >= spans[-1].end:
        return len(spans) - 1
    return bisect_right(starts, t) - 1


def total_duration(spans: list[Span]) -> float:
    """Where the timeline ends; zero for an empty timeline.

    >>> total_duration(allocate(["a", "bb"], 2.0))
    2.0
    """
    return spans[-1].end if spans else 0.0
