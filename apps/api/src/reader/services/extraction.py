"""Turn PDF bytes into the frozen :mod:`reader.domain.documents` value objects.

>>> doc = extract(render("Hello brave new world"), doc_id="abc123")
>>> doc.id, doc.page_count
('abc123', 1)
>>> doc.pages[0].text
'Hello brave new world'
"""

from __future__ import annotations

import uuid

import pymupdf

from reader.domain.documents import Box, Document, Page, Word


class EncryptedPDF(ValueError):
    """Raised when a PDF opens fine structurally but is locked behind a password.

    Distinct from the general "not a valid PDF" ValueError so callers (the
    route) can give the reader a wording that doesn't send them off to
    re-export a file that was never broken.
    """


def extract(
    pdf_bytes: bytes, *, filename: str = "document.pdf", doc_id: str | None = None
) -> Document:
    """Parse PDF bytes into a Document of pages, each holding its words in reading order.

    >>> extract(render("Hi there")).pages[0].words[0].text
    'Hi'
    """
    try:
        pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except pymupdf.FileDataError as exc:
        raise ValueError("not a valid PDF") from exc
    if pdf.is_encrypted:
        raise EncryptedPDF("PDF is password-protected")

    pages = []
    for index, page in enumerate(pdf):
        raw_words = sorted(page.get_text("words"), key=lambda w: (w[5], w[6], w[7]))
        words = tuple(
            Word(text=text, box=Box(x0=x0, y0=y0, x1=x1, y1=y1))
            for x0, y0, x1, y1, text, *_ in raw_words
        )
        pages.append(Page(index=index, width=page.rect.width, height=page.rect.height, words=words))

    return Document(id=doc_id or uuid.uuid4().hex[:12], filename=filename, pages=tuple(pages))


def render(text: str, *, page_size: tuple[float, float] = (612, 792)) -> bytes:
    """Lay `text` out as wrapped lines on one or more pages, for building test PDFs.

    >>> len(render("hello world")) > 0
    True
    """
    width, height = page_size
    margin, fontsize, leading = 72, 12, 16
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    x, y = margin, margin + fontsize
    for word in text.split():
        word_width = pymupdf.get_text_length(word, fontsize=fontsize)
        if x + word_width > width - margin:
            x, y = margin, y + leading
        if y > height - margin:
            page = doc.new_page(width=width, height=height)
            x, y = margin, margin + fontsize
        page.insert_text((x, y), word, fontsize=fontsize)
        x += word_width + pymupdf.get_text_length(" ", fontsize=fontsize)
    return doc.tobytes()
