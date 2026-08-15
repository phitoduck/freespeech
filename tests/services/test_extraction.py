"""Service-level tests for reader.services.extraction: real PyMuPDF, no server."""

from __future__ import annotations

import pymupdf
from reader.services.extraction import extract


def test_two_column_page_reads_one_column_at_a_time():
    """Words come out in the PDF's structural order, not geometric (y, x) order.

    Left column "Alpha L1 L2 ... L12", right column "Bravo R1 R2 ... R12",
    inserted left first. Structural order (what this pins) yields every left
    word before any right word:

        ["Alpha", "L1", ..., "L12", "Bravo", "R1", ..., "R12"]

    Geometric sort (page.get_text("words", sort=True)) orders by y then x, which
    cuts the right column in mid-sentence. Measured, with this exact input:

        [..., "L11", "Bravo", "R1", ..., "R10", "L12", "R11", "R12"]

    "L12" ends up stranded eleven words after the column it belongs to.
    """
    left_words = ["Alpha"] + [f"L{i}" for i in range(1, 13)]
    right_words = ["Bravo"] + [f"R{i}" for i in range(1, 13)]

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    left_box = pymupdf.Rect(60, 60, 290, 700)
    right_box = pymupdf.Rect(320, 60, 550, 700)
    page.insert_textbox(left_box, " ".join(left_words), fontsize=12, fontname="helv")
    page.insert_textbox(right_box, " ".join(right_words), fontsize=12, fontname="helv")
    pdf_bytes = doc.tobytes()

    document = extract(pdf_bytes)

    assert [w.text for w in document.pages[0].words] == left_words + right_words
