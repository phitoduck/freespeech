"""Group a page's words into synthesis units, each short enough that its
measured audio duration can re-anchor the karaoke timing estimate (ADR 0002).

>>> [s.text for s in split_sentences(["Dr.", "Smith", "left."])]
['Dr. Smith left.']
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ABBREVIATIONS = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr",
        "vs", "etc", "eg", "ie", "al", "fig", "no", "vol", "pp",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }
)

_CLOSERS = "\"')]}»”’"
_TERMINATORS = ".!?"
_INITIAL = re.compile(r"^[A-Z]\.$")
_BREAK_CHARS = frozenset(",;:-")  # a unit may end right after one, no audible jolt
_BULLETS = frozenset("●•▪-")  # glued onto the next word by extraction; a unit ends before one
_SPOKEN_BULLETS = "●•▪"  # dropped from .text only: Kokoro vocalises these (unlike "-", which it
# already ignores), so speaking them mismatches the duration speech_cost predicted

# A table-of-contents leader, which PyMuPDF glues into one token with no
# spaces: 'Introduction..............................1'. Kokoro reads the dots.
# The threshold is 4 rather than 1 because '...' and '…' are real punctuation
# and must survive; the tests carry the measurements.
_LEADER_RUN = re.compile(r"\.{4,}")

# Unpunctuated PDF content (bullet lists, headings, tables, CVs) once produced
# 262-word units -- ~80s of audio never re-anchored. 24 words is ~8-10s: short
# enough to keep drift inaudible, long enough to rarely cut mid-sentence.
MAX_UNIT_WORDS = 24


@dataclass(frozen=True, slots=True)
class Sentence:
    """A run of words and their position in the page's word list."""

    start: int
    words: tuple[str, ...]

    @property
    def stop(self) -> int:
        return self.start + len(self.words)

    @property
    def text(self) -> str:
        """Words joined for synthesis, with bullet glyphs and dot leaders
        removed -- Kokoro vocalises a bullet glyph as "black circle" and
        reads a leader's dots aloud one by one, both of which throw off the
        audio-duration estimate.

        >>> Sentence(start=0, words=("●Set", "up")).text
        'Set up'
        >>> Sentence(start=0, words=("Introduction....7",)).text
        'Introduction7'
        """
        table = str.maketrans("", "", _SPOKEN_BULLETS)
        spoken = " ".join(
            w for w in (_LEADER_RUN.sub("", word.translate(table)) for word in self.words) if w
        )
        # words were all-bullet/all-leader (or empty), e.g. ("●", "▪"): the fallback
        # must be audible, not merely non-empty -- Kokoro synthesises "", "-" and "•"
        # as silence (0.0s), and a zero-duration unit makes allocate() raise ValueError.
        # "bullet" is kept (not replaced with a more topical word for the leader
        # case) because it is the one fallback word actually measured audible
        # against the real model (0.86s, see tests/services/test_speech.py) --
        # swapping it for an unmeasured word risks reintroducing exactly the
        # silent-fallback bug this module already shipped once.
        return spoken or "bullet"


def _ends_sentence(token: str) -> bool:
    stripped = token.rstrip(_CLOSERS)
    if not stripped or stripped[-1] not in _TERMINATORS:
        return False
    if _INITIAL.match(stripped):
        return False
    return stripped.rstrip(_TERMINATORS).lower() not in _ABBREVIATIONS


def split_sentences(words: tuple[str, ...] | list[str]) -> list[Sentence]:
    """Split words into units of at most MAX_UNIT_WORDS words; concatenating
    the units' words reproduces the input, in order. A run with no terminator
    is cut at the rightmost comma/semicolon/colon/dash/bullet boundary in the
    window, or hard at the cap if the window has none.

    >>> [s.words for s in split_sentences(["Dr.", "Smith", "left.", "He", "ran"])]
    [('Dr.', 'Smith', 'left.'), ('He', 'ran')]
    >>> long_run = [f"w{i}" for i in range(30)]
    >>> long_run[10] = "w10,"
    >>> [len(s.words) for s in split_sentences(long_run)]
    [11, 19]
    """
    words = list(words)
    n = len(words)
    sentences: list[Sentence] = []
    start = 0
    while start < n:
        cap = start + MAX_UNIT_WORDS
        limit = min(cap, n)
        stop = limit
        natural = None
        for i in range(start, limit):
            if _ends_sentence(words[i]):
                stop = i + 1
                natural = None
                break
            if i > start and (
                words[i][:1] in _BULLETS or words[i - 1].rstrip(_CLOSERS)[-1:] in _BREAK_CHARS
            ):
                natural = i
        else:
            if limit == cap and natural is not None:
                stop = natural
        sentences.append(Sentence(start=start, words=tuple(words[start:stop])))
        start = stop
    return sentences
