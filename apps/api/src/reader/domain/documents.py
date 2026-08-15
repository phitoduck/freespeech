"""Document -> Page -> Word: frozen value objects for a parsed PDF.

>>> doc = Document("id", "f.pdf", (Page(0, 100, 200, (Word("cat", Box(0, 0, 10, 20)),)),))
>>> doc.page_count
1
>>> doc.page(0).text
'cat'
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Box:
    """A word's rectangle on the page, in PDF points, origin top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True, slots=True)
class Word:
    """One whitespace-delimited token, with the box to highlight it in."""

    text: str
    box: Box


@dataclass(frozen=True, slots=True)
class Page:
    """A page's words in reading order."""

    index: int
    width: float
    height: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


@dataclass(frozen=True, slots=True)
class Document:
    """A whole PDF, reduced to what a reader needs."""

    id: str
    filename: str
    pages: tuple[Page, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page(self, index: int) -> Page:
        if not 0 <= index < len(self.pages):
            raise IndexError(f"page {index} out of range (0..{len(self.pages) - 1})")
        return self.pages[index]
