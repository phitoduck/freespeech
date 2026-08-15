"""BDD bindings for the ``@docs`` scenarios of features/upload.feature.

These drive a real browser (Playwright) against the real app -- the real
FastAPI backend and the Vite dev server for the frontend, wired up by the
``app_servers``/``visit_app``/``drop_file``/``word_locator``/``shot`` fixtures
in tests/bdd/conftest.py. Only the ``@docs`` scenarios are bound here, via
explicit ``scenario()`` decorators; the ``@property`` scenarios in this
feature file are bound in test_upload_properties.py and stay unbound here.

These two scenarios also generate the tutorial's first two screenshots (see
docs/tutorials/read-your-first-pdf.md and ADR 0004):
dropping-a-one-page-pdf-reveals-its-text/01-empty.png and .../02-loaded.png.
"""

from __future__ import annotations

import pymupdf
from playwright.sync_api import expect
from pytest_bdd import given, parsers, scenario, then
from reader.services.extraction import render


@scenario("upload.feature", "Dropping a one-page PDF reveals its text")
def test_dropping_a_one_page_pdf_reveals_its_text():
    pass


@scenario("upload.feature", "A PDF with no readable text says so instead of going blank")
def test_a_pdf_with_no_readable_text_says_so_instead_of_going_blank():
    pass


@scenario("upload.feature", "A non-PDF file is rejected without breaking the page")
def test_a_non_pdf_file_is_rejected_without_breaking_the_page():
    pass


@scenario("upload.feature", "A password-protected PDF says it is locked, not that it is broken")
def test_a_password_protected_pdf_says_it_is_locked_not_that_it_is_broken():
    pass


@scenario("upload.feature", "A corrupt file named .pdf is reported once, clearly")
def test_a_corrupt_file_named_pdf_is_reported_once_clearly():
    pass


@given(parsers.parse('a file named "{name}" containing "{content}"'), target_fixture="dropped_file")
def _a_non_pdf_file(name: str, content: str) -> dict:
    return {"name": name, "mimeType": "text/plain", "buffer": content.encode()}


@given("a PDF containing no text at all", target_fixture="dropped_file")
def _a_pdf_containing_no_text_at_all() -> dict:
    """A single blank page -- what a scanned PDF looks like to the extractor.

    >>> buffer = _a_pdf_containing_no_text_at_all()["buffer"]
    >>> pymupdf.open(stream=buffer, filetype="pdf")[0].get_text("words")
    []
    """
    doc = pymupdf.open()
    doc.new_page()
    return {"name": "scan.pdf", "mimeType": "application/pdf", "buffer": doc.tobytes()}


@given("a password-protected PDF", target_fixture="dropped_file")
def _a_password_protected_pdf() -> dict:
    """A PDF pymupdf can build fine but only opens with the right password.

    >>> buffer = _a_password_protected_pdf()["buffer"]
    >>> pymupdf.open(stream=buffer, filetype="pdf").is_encrypted
    True
    """
    doc = pymupdf.open(stream=render("Secret quarterly results."), filetype="pdf")
    buffer = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="hunter2"
    )
    return {"name": "locked.pdf", "mimeType": "application/pdf", "buffer": buffer}


@given(parsers.parse('a corrupt file named "{name}"'), target_fixture="dropped_file")
def _a_corrupt_file_named(name: str) -> dict:
    """Bytes that are not a PDF at all, wearing a ``.pdf`` name.

    >>> _a_corrupt_file_named("broken.pdf")["name"]
    'broken.pdf'
    """
    return {
        "name": name,
        "mimeType": "application/pdf",
        "buffer": b"this is garbage, not a pdf at all",
    }


@then("the reader shows 1 page")
def _the_reader_shows_1_page(page):
    expect(page.get_by_test_id("page-view")).to_be_visible(timeout=15000)


@then("the play button is enabled")
def _the_play_button_is_enabled(page, shot):
    expect(page.get_by_test_id("play-button")).to_be_enabled(timeout=30000)
    shot("02-loaded")


# Screenshot name per error message -- each rejection scenario gets its own
# named doc image; anything not listed here keeps the original "02-rejected".
_ERROR_SHOT_NAMES = {"That PDF has no readable text — it may be a scan": "02-no-text"}


@then(parsers.parse('I see the error "{message}"'))
def _i_see_the_error(page, shot, message: str):
    expect(page.get_by_role("alert")).to_have_text(message)
    shot(_ERROR_SHOT_NAMES.get(message, "02-rejected"))


@then("the drop zone is still ready to accept a file")
def _the_drop_zone_is_still_ready(page):
    expect(page.get_by_test_id("drop-zone")).to_be_visible()
    expect(page.locator('[data-testid="drop-zone"] input[type="file"]')).to_be_attached()
