# 6. Word order follows the PDF's own structure, not the geometry

- Status: accepted
- Date: 2026-08-15

## Context

The reader speaks a page one word at a time, so the order it puts words in *is*
the order it reads them aloud. Get it wrong and the narration is fluent
nonsense.

PyMuPDF offers two orderings, and they are not the same:

| | how it orders | |
|---|---|---|
| **structural** | `(block_no, line_no, word_no)` — the order the PDF's own content stream declares | what the producer meant |
| **geometric** | `get_text("words", sort=True)` — top to bottom, then left to right | what the pixels look like |

Geometric sorting is the one that sounds safer, and it is the change most
likely to be proposed as a tidy-up.

## Decision

Sort structurally:

```python
raw_words = sorted(page.get_text("words"), key=lambda w: (w[5], w[6], w[7]))
```

## Consequences

- **Multi-column pages read correctly.** On a two-column page the reader speaks
  the left column all the way down, then the right — because that is how the
  producer emitted it.
- **Geometric sorting would break exactly that case.** Sorting by `y` then `x`
  interleaves the columns line by line: `Alpha Bravo L1 R1 L2 R2 …`. Measured,
  not assumed. This is the trap: it is a one-line "improvement" that looks
  tidier and destroys any document with columns, so
  `tests/services/test_extraction.py` pins the column-by-column order and fails
  if someone makes it.
- **The limitation is inherited from the producer.** A PDF whose content stream
  emits the right column before the left is read right column first. Building
  one deliberately confirms it. Fixing that needs real column detection —
  clustering words into regions and ordering the regions — which is a
  disproportionate amount of machinery for a local prototype, and would risk the
  common case to rescue an uncommon one.
- **On real documents this has not come up.** Nine PDFs to hand — résumés,
  proposals, course material, 2,653 words — all extract in an order matching
  what a person reads.

    !!! warning "That last measurement is weaker than it looks"
        It was first made by comparing the extracted words against
        `page.get_text("text")` and finding no divergence on any of the nine.
        That proved almost nothing: `get_text("text")` follows the *same*
        content-stream order as `get_text("words")`, so the check was comparing
        the implementation against itself. It reported `MATCH` even for the
        deliberately-broken PDF that reads its columns backwards.

        The number is kept because it is still evidence that these documents are
        ordinary, but the independent evidence is the constructed two-column
        case, where the two orderings genuinely disagree.
