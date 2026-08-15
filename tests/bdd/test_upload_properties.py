"""BDD bindings for the ``@property`` scenarios of features/upload.feature.

Only the ``@property`` scenarios are bound here, via explicit ``scenario()``
decorators (not ``scenarios()``) — the ``@docs`` scenarios in that file are
implemented elsewhere and must stay unbound in this module. See
test_karaoke_properties.py for the integration pattern this follows.
"""

from __future__ import annotations

from hypothesis import given as for_all
from pytest_bdd import given, scenario, then, when
from reader.services.extraction import extract, render

from tests.properties.strategies import word_lists

# Rendering/extraction round-trips through PyMuPDF; allow a hair of tolerance
# for glyph-metric rounding at page/box edges.
_TOL = 1e-6


@scenario("upload.feature", "Any text survives the round trip through a PDF")
def test_text_survives_the_round_trip_through_a_pdf():
    pass


@scenario("upload.feature", "Every extracted word carries a usable highlight box")
def test_every_extracted_word_carries_a_usable_highlight_box():
    pass


@given("any document of words", target_fixture="document_words_strategy")
def _document_words_strategy():
    return word_lists()


@when("it is rendered to a PDF and extracted again", target_fixture="round_trip_op")
def _round_trip_op():
    def op(words):
        pdf_bytes = render(" ".join(words))
        return extract(pdf_bytes, filename="roundtrip.pdf")

    return op


@then("the extracted words are exactly the original words, in order")
def _extracted_words_match_the_original(document_words_strategy, round_trip_op):
    @for_all(document_words_strategy)
    def check(words):
        document = round_trip_op(words)
        extracted = [word.text for page in document.pages for word in page.words]
        assert extracted == words

    check()


@then("every word has a box with positive width and height")
def _every_box_has_positive_size(document_words_strategy, round_trip_op):
    @for_all(document_words_strategy)
    def check(words):
        document = round_trip_op(words)
        for page in document.pages:
            for word in page.words:
                assert word.box.width > 0
                assert word.box.height > 0

    check()


@then("every word's box lies inside its page")
def _every_box_lies_inside_its_page(document_words_strategy, round_trip_op):
    @for_all(document_words_strategy)
    def check(words):
        document = round_trip_op(words)
        for page in document.pages:
            for word in page.words:
                box = word.box
                assert -_TOL <= box.x0 <= box.x1 <= page.width + _TOL
                assert -_TOL <= box.y0 <= box.y1 <= page.height + _TOL

    check()
