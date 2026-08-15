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
# Dropped from the spoken form wherever they appear. Kokoro vocalises a bullet glyph
# ("black circle"), so speaking one mismatches the predicted duration; U+200B is a
# zero-width space, invisible on the page and 0.0s of audio, but it splits a vowel run
# and so invents a syllable ('a​a' scores 2, 'aa' scores 1).
_DROP_ALWAYS = str.maketrans("", "", "●•▪​")

# '-', '–' and '^^' each measured 0.0s of audio as a whole token; a run of solely these
# generalises from that. Meaningful inside a word, though, so only a token that is
# nothing but them is dropped -- 'well-known' and '-5' keep their hyphen.
_SILENT_ALONE = "-–^"

# A table-of-contents leader, which PyMuPDF glues into one token with no
# spaces: 'Introduction..............................1'. Kokoro reads the dots.
# The threshold is 4 rather than 1 because '...' and '…' are real punctuation
# and must survive; the tests carry the measurements.
_LEADER_RUN = re.compile(r"\.{4,}")

# Unpunctuated PDF content (bullet lists, headings, tables, CVs) once produced
# 262-word units -- ~80s of audio never re-anchored. 24 words is ~8-10s: short
# enough to keep drift inaudible, long enough to rarely cut mid-sentence.
MAX_UNIT_WORDS = 24


def spoken(word: str) -> str:
    """The part of a token the synthesiser actually voices. Empty when the
    token is pure layout -- a bullet or a leader, which the model reads aloud
    but nobody wants read, or a bare dash, which it renders as 0.0s of audio.

    The single source of truth for "what is said for this word" -- both the
    text sent to Kokoro (Sentence.text) and the timing weight given to the
    word (timeline.speech_cost) come from here, or they drift apart and the
    highlight stops matching the voice.

    >>> spoken("●Set")
    'Set'
    >>> spoken("Introduction....7")
    'Introduction7'
    >>> spoken("..........")
    ''
    >>> spoken("-"), spoken("well-known")   # bare dash vs hyphen in a word
    ('', 'well-known')
    """
    said = _LEADER_RUN.sub("", word.translate(_DROP_ALWAYS))
    return said if said.strip(_SILENT_ALONE) else ""


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
        said = " ".join(filter(None, map(spoken, self.words)))
        # Fallback for all-bullet/all-leader words, e.g. ("●", "▪"): must be audible,
        # not merely non-empty -- Kokoro synthesises "", "-" and "•" as silence
        # (0.0s), and a zero-duration unit makes allocate() raise. "bullet" stays
        # because it is the one fallback measured audible against the real model
        # (0.86s, tests/services/test_speech.py); swapping in an unmeasured word
        # risks reintroducing exactly that silent-fallback bug.
        return said or "bullet"


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
