"""BDD bindings for the ``@docs`` scenarios of features/karaoke.feature.

Real browser, real app, real Kokoro model -- see tests/bdd/conftest.py for the
``app_servers``/``visit_app``/``drop_file``/``word_locator``/``shot`` fixtures
this reuses. Only the ``@docs`` scenarios are bound here, via explicit
``scenario()`` decorators; the ``@property`` scenarios in this feature file
are bound in test_karaoke_properties.py and stay unbound here.

Several of these scenarios generate documentation artefacts (ADR 0004):
"Pressing play..." writes pressing-play-starts-the-narration-and-lights-the-
first-word/03-playing.png, "Clicking a word..." writes clicking-a-word-jumps-
the-narration-to-it/04-jumped.png, "Moving to the next page..." writes
moving-to-the-next-page/05-page-two.png, and the ``@gif``-tagged "The
highlight advances..." records docs/assets/generated/karaoke/karaoke.gif,
since a still image cannot show the highlight moving.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from playwright.sync_api import expect
from pytest_bdd import given, parsers, scenario, then, when
from reader.services.extraction import render

REPO_ROOT = Path(__file__).resolve().parents[2]
GIF_PATH = REPO_ROOT / "docs" / "assets" / "generated" / "karaoke" / "karaoke.gif"


@scenario("karaoke.feature", "Pressing play starts the narration and lights the first word")
def test_pressing_play_starts_the_narration_and_lights_the_first_word():
    pass


@scenario("karaoke.feature", "The highlight advances through the page as the audio plays")
def test_the_highlight_advances_through_the_page_as_the_audio_plays():
    pass


@scenario("karaoke.feature", "The highlighted word is visibly distinct from the words around it")
def test_the_highlighted_word_is_visibly_distinct_from_the_words_around_it():
    pass


@scenario("karaoke.feature", "Pausing freezes the highlight where it is")
def test_pausing_freezes_the_highlight_where_it_is():
    pass


@scenario("karaoke.feature", "Clicking a word jumps the narration to it")
def test_clicking_a_word_jumps_the_narration_to_it():
    pass


@scenario("karaoke.feature", "Moving to the next page")
def test_moving_to_the_next_page():
    pass


@scenario("karaoke.feature", "Going back to re-read the previous page")
def test_going_back_to_re_read_the_previous_page():
    pass


@scenario("karaoke.feature", "A slow page never overwrites the page that replaced it")
def test_a_slow_page_never_overwrites_the_page_that_replaced_it():
    pass


@scenario("karaoke.feature", "A one-page PDF shows no page controls at all")
def test_a_one_page_pdf_shows_no_page_controls_at_all():
    pass


@scenario("karaoke.feature", "A blank page says so instead of looking broken")
def test_a_blank_page_says_so_instead_of_looking_broken():
    pass


_GIF_FRAME_SECONDS = 0.2
"""One documentation GIF frame per this many seconds of narration (5fps)."""


def _frange(start: float, stop: float, step: float) -> list[float]:
    """The instants to sample, inclusive of both ends.

    >>> _frange(0.0, 0.5, 0.2)
    [0.0, 0.2, 0.4, 0.5]
    """
    out = [start]
    while out[-1] + step < stop:
        out.append(out[-1] + step)
    out.append(stop)
    return out


_ACTIVE_SEEN_LATCH = """() => {
    window.__activeSeen = [];
    const record = () => {
        const el = document.querySelector('[data-active="true"]');
        if (el) {
            const i = Number(el.dataset.wordIndex);
            if (window.__activeSeen.at(-1) !== i) window.__activeSeen.push(i);
        }
    };
    record();
    new MutationObserver(record).observe(document.body, {
        subtree: true, attributes: true, attributeFilter: ["data-active"],
    });
}"""


@given("I have dropped it onto the drop zone")
def _i_have_dropped_it_onto_the_drop_zone(page, drop_file, dropped_file, state):
    with page.expect_response(lambda r: "/narration" in r.url, timeout=45000) as response_info:
        drop_file(dropped_file)
    state["narration"] = response_info.value.json()
    expect(page.get_by_test_id("play-button")).to_be_enabled(timeout=30000)
    # Latch, in the page, every word index the highlight ever visits -- a live
    # poll (even Playwright's own `expect()`, which backs off between polls)
    # samples at intervals of the same order as how long a single word stays
    # active and can step right over a transient. A MutationObserver
    # installed before playback starts cannot miss a change, however brief.
    page.evaluate(_ACTIVE_SEEN_LATCH)


_TOGGLED_LABEL = {"play": "Pause", "pause": "Play"}


@when(parsers.parse("I press {action}"))
def _i_press(page, action: str):
    page.get_by_test_id("play-button").click()
    expect(page.get_by_test_id("play-button")).to_have_text(_TOGGLED_LABEL[action], timeout=10000)


def _assemble_gif(frames_dir: Path, output_path: Path) -> None:
    """ffmpeg two-pass palette encode, per ADR 0004's "docs images are test output" rule."""
    palette = frames_dir / "palette.png"
    raw_gif = frames_dir / "out.gif"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", "5", "-i", "frame_%03d.png",
         "-vf", "palettegen", str(palette)],
        cwd=frames_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", "5", "-i", "frame_%03d.png",
            "-i", str(palette), "-lavfi", "paletteuse", str(raw_gif),
        ],
        cwd=frames_dir,
        check=True,
        capture_output=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(raw_gif), str(output_path))


@when("the audio reaches the end of the first sentence")
def _the_audio_reaches_the_end_of_the_first_sentence(page, word_locator, state):
    """Advance the narration into the second sentence, recording the docs GIF on the way.

    Playback genuinely starts (the previous step asserts the button flips to
    "Pause"), but this host's Chromium never advances the media clock -- even a
    bare 440Hz WAV in a plain `<audio>` freezes at 0.042667s with readyState 4
    and the file fully buffered. So the harness drives the playhead itself and
    lets the app's own rAF loop map it to the highlight; that mapping is what
    this project promises, Chromium's audio renderer is not ours to test.

    Leaves the playhead parked inside "Kokoro" so the Then steps below read a
    live DOM, not a remembered one.
    """
    spans = state["narration"]["spans"]
    duration = state["narration"]["duration"]
    kokoro_index = int(word_locator("Kokoro").get_attribute("data-word-index"))

    frames_dir = Path(tempfile.mkdtemp(prefix="karaoke-frames-"))
    area = page.locator('[data-testid="page-view"]')
    try:
        for i, t in enumerate(_frange(0.0, duration, _GIF_FRAME_SECONDS)):
            page.eval_on_selector("audio", "(el, t) => { el.currentTime = t; }", t)
            area.screenshot(path=str(frames_dir / f"frame_{i:03d}.png"))
        _assemble_gif(frames_dir, GIF_PATH)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    visited = page.evaluate("window.__activeSeen")
    assert kokoro_index in visited, f"highlight never reached 'Kokoro'; visited {visited}"
    assert visited == sorted(visited), f"highlight moved backwards through the page: {visited}"

    kokoro_span = next(s for s in spans if s["word_index"] == kokoro_index)
    parked = kokoro_span["start"] + min(0.01, (kokoro_span["end"] - kokoro_span["start"]) / 2)
    page.eval_on_selector("audio", "(el, t) => { el.currentTime = t; }", parked)


@when(parsers.parse('I click the word "{word}"'))
def _i_click_the_word(word_locator, word: str):
    word_locator(word).click()


@then("audio is playing")
def _audio_is_playing(page, shot):
    expect(page.get_by_test_id("play-button")).to_have_text("Pause")
    assert page.eval_on_selector("audio", "el => !el.paused")
    shot("03-playing")


@then("audio is not playing")
def _audio_is_not_playing(page):
    expect(page.get_by_test_id("play-button")).to_have_text("Play")
    assert page.eval_on_selector("audio", "el => el.paused")


_ACTIVE_ATTR = {"highlighted": "true", "no longer highlighted": "false"}


@then(parsers.parse('the word "{word}" is {state}'))
def _the_word_is_in_state(word_locator, word: str, state: str):
    expect(word_locator(word)).to_have_attribute("data-active", _ACTIVE_ATTR[state], timeout=10000)


@then("no other word is highlighted")
@then("exactly one word is still highlighted")
def _exactly_one_word_is_highlighted(page):
    expect(page.locator('[data-active="true"]')).to_have_count(1)


def _rgb(css: str) -> tuple[int, int, int]:
    """Parse a CSS rgb()/rgba() colour into its channels.

    >>> _rgb("rgb(246, 215, 140)")
    (246, 215, 140)
    >>> _rgb("rgba(0, 0, 0, 0)")
    (0, 0, 0)
    """
    return tuple(int(n) for n in css.split("(")[1].split(")")[0].split(",")[:3])


# Sum of absolute R/G/B differences. The real highlight (#f6d78c) is 134 apart
# from the page background (#faf6ef); 60 is comfortably below that but well
# above anti-aliasing noise, so a near-invisible highlight still fails this.
_MIN_COLOUR_DISTANCE = 60

# Walk up from `el` past any transparent background to the colour that is
# actually painted, since an unstyled span inherits its visible background.
_BACKGROUND_JS = """(el) => {
    let node = el;
    while (node && getComputedStyle(node).backgroundColor === "rgba(0, 0, 0, 0)") {
        node = node.parentElement;
    }
    node = node || document.body;
    return getComputedStyle(node).backgroundColor;
}"""


def _distinct(a: str, b: str) -> bool:
    """Whether two CSS colours are far enough apart to be visibly different.

    >>> _distinct("rgb(246, 215, 140)", "rgb(250, 246, 239)")  # highlight vs page
    True
    >>> _distinct("rgb(250, 246, 239)", "rgb(250, 246, 239)")  # invisible highlight
    False
    """
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return abs(ar - br) + abs(ag - bg) + abs(ab - bb) >= _MIN_COLOUR_DISTANCE


@then("the highlighted word has a different background from the page")
def _highlighted_word_differs_from_page(page):
    active_bg = page.eval_on_selector('[data-active="true"]', _BACKGROUND_JS)
    page_bg = page.eval_on_selector("body", _BACKGROUND_JS)
    assert _distinct(active_bg, page_bg), f"highlight {active_bg} too close to page {page_bg}"


@then("the highlighted word has a different background from its neighbours")
def _highlighted_word_differs_from_neighbours(page):
    active_bg = page.eval_on_selector('[data-active="true"]', _BACKGROUND_JS)
    active_index = int(page.locator('[data-active="true"]').get_attribute("data-word-index"))
    for offset in (-1, 1):
        neighbour = page.locator(f'.karaoke-word[data-word-index="{active_index + offset}"]')
        if neighbour.count() == 0:
            continue
        neighbour_bg = neighbour.evaluate(_BACKGROUND_JS)
        assert _distinct(active_bg, neighbour_bg), (
            f"highlight {active_bg} too close to neighbour {neighbour_bg}"
        )


@then(parsers.parse('the narration position is at the word "{word}"'))
def _the_narration_position_is_at_the_word(page, word_locator, state, word: str, shot):
    index = int(word_locator(word).get_attribute("data-word-index"))
    span = next(s for s in state["narration"]["spans"] if s["word_index"] == index)
    current_time = page.eval_on_selector("audio", "el => el.currentTime")
    assert abs(current_time - span["start"]) < 0.25
    shot("04-jumped")


@given(
    parsers.parse('a two-page PDF reading "{first}" and "{second}"'),
    target_fixture="dropped_file",
)
def _a_two_page_pdf_reading(first: str, second: str) -> dict:
    """Two single-page PDFs, concatenated into one two-page document.

    >>> buffer = _a_two_page_pdf_reading("One.", "Two.")["buffer"]
    >>> pymupdf.open(stream=buffer, filetype="pdf").page_count
    2
    """
    a = pymupdf.open(stream=render(first), filetype="pdf")
    b = pymupdf.open(stream=render(second), filetype="pdf")
    a.insert_pdf(b)
    return {"name": "two-page.pdf", "mimeType": "application/pdf", "buffer": a.tobytes()}


@given("a three-page PDF", target_fixture="dropped_file")
def _a_three_page_pdf() -> dict:
    """Three pages, each with a distinctive first word AND a different word count,
    so that swapping any page's words for another's is unambiguous either way.

    >>> doc = pymupdf.open(stream=_a_three_page_pdf()["buffer"], filetype="pdf")
    >>> doc.page_count
    3
    """
    texts = [
        "Alpha starts the story.",
        "Beta carries the story further along than before.",
        "Gamma finally brings the whole long story to its very last close.",
    ]
    doc = pymupdf.open(stream=render(texts[0]), filetype="pdf")
    for text in texts[1:]:
        doc.insert_pdf(pymupdf.open(stream=render(text), filetype="pdf"))
    return {"name": "three-page.pdf", "mimeType": "application/pdf", "buffer": doc.tobytes()}


@given("a three-page PDF whose middle page is blank", target_fixture="dropped_file")
def _a_three_page_pdf_whose_middle_page_is_blank() -> dict:
    """Built with PyMuPDF directly, not `reader.services.extraction.render` (used for
    every other PDF fixture in this file): `render` lays out text and cannot produce
    a page with none, which is the whole point of this fixture.

    >>> doc = pymupdf.open(
    ...     stream=_a_three_page_pdf_whose_middle_page_is_blank()["buffer"], filetype="pdf"
    ... )
    >>> [page.get_text().strip() for page in doc]
    ['First page has words here.', '', 'Third page has words too.']
    """
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    p.insert_textbox(
        pymupdf.Rect(60, 60, 550, 700), "First page has words here.", fontsize=12, fontname="helv"
    )
    doc.new_page(width=612, height=792)  # deliberately blank
    p = doc.new_page(width=612, height=792)
    p.insert_textbox(
        pymupdf.Rect(60, 60, 550, 700), "Third page has words too.", fontsize=12, fontname="helv"
    )
    return {"name": "blank-middle.pdf", "mimeType": "application/pdf", "buffer": doc.tobytes()}


def _wait_until(page, predicate, *, timeout_ms: int = 20000, interval_ms: int = 50) -> None:
    """Poll ``predicate`` on Playwright's own cooperative loop (via ``wait_for_timeout``,
    which yields control so route handlers running in other greenlets can progress)
    until it is true, or raise once ``timeout_ms`` has elapsed.

    Needs a real ``page`` to demonstrate, so this is a comment, not a doctest:

    # -> _wait_until(page, lambda: landed[2])
    # -> blocks, calling page.wait_for_timeout(50) in a loop, until some other
    #    route handler (running on Playwright's dispatcher greenlet, which
    #    wait_for_timeout hands control to) sets landed[2] = True

    Playwright's sync API runs test code and route handlers as cooperating
    greenlets on one thread; only a Playwright call like ``wait_for_timeout``
    switches to the dispatcher greenlet that lets route handlers run.
    ``time.sleep`` would block that one thread outright and deadlock the two
    route handlers waiting on each other. ``page.wait_for_function`` doesn't
    apply either: the predicates polled here (``landed[1]``/``landed[2]``) are
    plain Python state in this test process, not anything evaluable in the
    page's DOM/JS context.
    """
    waited = 0
    while not predicate():
        if waited >= timeout_ms:
            raise TimeoutError(f"condition not met within {timeout_ms}ms")
        page.wait_for_timeout(interval_ms)
        waited += interval_ms


_NARRATION_PAGE_RE = re.compile(r"/pages/(\d+)/narration")


@when("I move forward twice and the first request answers last")
def _i_move_forward_twice_and_the_first_request_answers_last(page, app_servers, state):
    """Let both narration requests really run, but hold page 1's finished answer back
    until page 2's has already reached the browser -- deterministically forcing the
    exact overlap the bug report reproduced, regardless of which page's Kokoro
    synthesis actually finishes first.

    One route, matching any page's narration request, tells page 1 and page 2 apart
    by parsing the page number back out of the URL (``_NARRATION_PAGE_RE``) rather
    than registering a separate handler per page -- the two only ever differed in
    whether they wait, not in how they fetch or record. Each still stashes the
    narration JSON it fetched into ``state`` (keyed by page index) so the ``Then``
    step can compare the page that ends up on screen against the narration that
    page's own request actually returned.

    The route rewrites the web origin to the real API port itself
    (``_to_api``), even though ``visit_app`` already installs a rewrite route for
    ``/api/**``: Playwright tries routes most-recently-registered first
    (``page.py``'s ``route()`` does ``self._routes.insert(0, ...)``), and neither
    handler here calls ``route.fallback()``, so this route always wins the match
    and ``visit_app``'s never runs for these URLs at all -- the rewrite has to be
    done again here or ``route.fetch()`` would hit the Vite dev server, not the API.

    Blocks until page 1's held-back response has actually been delivered to the
    browser (plus a short settle buffer for React to act on it) -- otherwise the
    ``Then`` step's own polling could read the DOM in the brief in-between window
    where page 2's (correct) narration is still showing, and the race this step
    exists to force would go unobserved.
    """
    api_url = app_servers["api"]
    web_url = app_servers["web"]
    state["narrations_by_page"] = {}
    landed = {1: False, 2: False}

    def _to_api(url: str) -> str:
        """Rewrite this step's own fetch from the web origin to the real API port.

        # -> _to_api("http://localhost:5173/api/documents/x/pages/1/narration")
        # -> "http://localhost:8000/api/documents/x/pages/1/narration"
        (using this closure's captured web_url/api_url; see the step's docstring
        for why this route can't just rely on visit_app's rewrite route instead)
        """
        return url.replace(web_url, api_url, 1)

    def _handle_narration(route):
        """Fetch the real response, hold page 1's back until page 2's has landed,
        then deliver it -- so page 1's (stale) response always arrives last.

        # -> a request for .../pages/2/narration is fetched and fulfilled
        #    immediately, then landed[2] is set to True
        # -> a request for .../pages/1/narration is fetched, then blocks until
        #    landed[2] is True before it is fulfilled and landed[1] is set
        """
        page_no = int(_NARRATION_PAGE_RE.search(route.request.url).group(1))
        response = route.fetch(url=_to_api(route.request.url))
        state["narrations_by_page"][page_no] = response.json()
        if page_no == 1:
            _wait_until(page, lambda: landed[2])
        route.fulfill(response=response)
        landed[page_no] = True

    page.route(f"{web_url}/api/documents/*/pages/*/narration**", _handle_narration)

    page.get_by_test_id("next-page").click()
    page.get_by_test_id("next-page").click()

    _wait_until(page, lambda: landed[1])
    page.wait_for_timeout(300)  # let React parse page 1's response and re-render


_AUDIO_PAGE_RE = re.compile(r"/pages/(\d+)/audio\.wav")


@then("the words on screen and the narration are for the same page")
def _the_words_on_screen_and_the_narration_are_for_the_same_page(page, state):
    """The indicator ("Page N of M") counts from 1; the audio URL's page segment counts
    from 0 -- e.g. "Page 3 of 3" pairs with a correct audio src of ".../pages/2/audio.wav".

    Waits for both in-flight requests to settle (the ``When`` step's route handlers
    keep running on this same event loop while ``expect`` polls here), then checks
    two independent signals of the one invariant: the audio src's page number must
    match the displayed page, and the number of words on screen must match the
    span count of whichever page's narration actually won the race.
    """
    expect(page.get_by_test_id("play-button")).to_be_enabled(timeout=45000)
    indicator = page.get_by_text(re.compile(r"^Page \d+ of \d+$"))
    expect(indicator).to_be_visible(timeout=15000)
    displayed_page = int(re.search(r"Page (\d+) of \d+", indicator.inner_text()).group(1)) - 1

    audio_src = page.eval_on_selector("audio", "el => el.getAttribute('src')")
    audio_page = int(_AUDIO_PAGE_RE.search(audio_src).group(1))

    assert audio_page == displayed_page, (
        f"indicator shows page {displayed_page + 1} but audio src is for page "
        f"{audio_page} ({audio_src!r})"
    )

    word_count = page.locator(".karaoke-word").count()
    winning_narration = state["narrations_by_page"][audio_page]
    assert word_count == len(winning_narration["spans"]), (
        f"{word_count} words on screen but the loaded narration (page {audio_page}) "
        f"has {len(winning_narration['spans'])} spans"
    )


@then(parsers.parse('I see "{text}"'))
def _i_see(page, shot, text: str):
    """Also takes the "Moving to the next page" doc screenshot.

    That's the only scenario (and the only place in this feature) that asserts
    "Page 2 of 2", so gating the shot on that exact text captures the page-two
    state exactly once, without the "I go to the next page" step -- shared
    with "Going back to re-read the previous page" -- writing it twice.
    """
    expect(page.get_by_text(text, exact=True)).to_be_visible(timeout=15000)
    if text == "Page 2 of 2":
        shot("05-page-two")


def _navigate_page(page, testid: str) -> None:
    """Click a page-nav button and wait for it to trigger a real re-fetch.

    The play button cycling disabled-then-enabled proves the narration was
    actually re-fetched, not just the on-screen words swapped.
    """
    page.get_by_test_id(testid).click()
    expect(page.get_by_test_id("play-button")).to_be_disabled(timeout=5000)
    expect(page.get_by_test_id("play-button")).to_be_enabled(timeout=45000)


@when("I go to the next page")
def _i_go_to_the_next_page(page):
    _navigate_page(page, "next-page")


@when("I go to the previous page")
def _i_go_to_the_previous_page(page, shot):
    """Also asserts the previous button itself disables, since page 1 is the first page."""
    _navigate_page(page, "previous-page")
    expect(page.get_by_test_id("previous-page")).to_be_disabled()
    shot("06-page-one-again")


@then("there are no page controls")
def _there_are_no_page_controls(page):
    expect(page.get_by_test_id("page-view")).to_be_visible(timeout=15000)
    expect(page.locator('[data-testid="page-controls"]')).to_have_count(0)


@when("I advance to the next page")
def _i_advance_to_the_next_page(page):
    """Deliberately not this file's shared `_navigate_page` (bound to "I go to
    the next page"): that step asserts the play button re-enables once the new
    page's narration has loaded, which is right for every other page in this
    suite but wrong for the blank page this scenario navigates onto -- Play is
    supposed to stay disabled there. Reusing it would make this scenario fail on
    an assertion belonging to a different page's behaviour instead of its own.
    """
    page.get_by_test_id("next-page").click()


@then("the play button is disabled")
def _the_play_button_is_disabled(page, shot):
    expect(page.get_by_test_id("play-button")).to_be_disabled(timeout=15000)
    shot("02-blank-page")
