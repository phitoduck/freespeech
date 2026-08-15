"""Shared fixtures for the ``@docs`` UI scenarios (Playwright, real app, real Kokoro).

Only the ``@docs`` scenarios of features/upload.feature and features/karaoke.feature
are exercised here — the ``@property`` scenarios use a completely different
(no-browser) fixture set in test_upload_properties.py/test_karaoke_properties.py.

Port constraint: the API gets a fresh free port every run (other agents may have
their own instance on the "usual" 8000), but the web app cannot -- its dev server
port is hardcoded to 5173 in the off-limits `vite.config.ts`, and the off-limits
CORS middleware only allows the exact origin `http://localhost:5173`. The
frontend's own `fetch("/api/...")` then resolves same-origin against that fixed
port, whose Vite proxy is hardcoded to API port 8000 -- not our freshly
discovered one. `visit_app` closes that gap with a Playwright network route that
rewrites `http://localhost:5173/api/**` to the real API port before the request
leaves the browser, so the browser still sees (and CORS-checks) origin 5173
regardless of where the API actually landed.

Flow: `app_servers` starts the API on a free port + reuses/starts Vite on 5173
-> `visit_app()` navigates and installs the rewrite route -> a step calls
`drop_file(...)`, the page fetches `/api/documents`, and the route sends it to
the real API port transparently.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import expect
from pytest_bdd import given, parsers, then, when
from reader.services.extraction import render

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "apps" / "web"

# Fixed by apps/web/vite.config.ts (dev server port) and reader/app.py (CORS
# allow-list) -- both off limits to this suite, so this is not a free choice.
WEB_PORT = 5173
WEB_URL = f"http://localhost:{WEB_PORT}"

SCREENSHOT_ROOT = REPO_ROOT / "docs" / "assets" / "generated"


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (local only)
            return resp.status < 500
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def _wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _http_ok(url):
            return True
        time.sleep(0.5)
    return False


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    """Chrome refuses `audio.play()` without a user gesture, and even a trusted
    Playwright click doesn't satisfy the default autoplay heuristic reliably
    enough for CI-style headless runs -- disable the policy outright."""
    return {
        **browser_type_launch_args,
        "args": [
            *browser_type_launch_args.get("args", []),
            "--autoplay-policy=no-user-gesture-required",
        ],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Fixed viewport so every generated documentation screenshot is the same size.

    The app's content column is centered and capped at 42rem (~624px) by CSS
    that is off limits to this suite, so a wide viewport alone would just add
    dead space around it (see the `shot` fixture below, which crops to that
    column) rather than making the content itself bigger. A higher device
    scale factor is the lever this suite actually has for legible documentation
    images: ~624 CSS px * 1.6 ~= 1000 physical px.
    """
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "device_scale_factor": 1.6,
    }


@pytest.fixture(scope="session")
def app_servers() -> Iterator[dict[str, str]]:
    """Start the real API on a fresh free port; start (or reuse) the Vite dev server."""
    api_port = _free_port()
    api_url = f"http://127.0.0.1:{api_port}"

    api_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "--extra",
            "tts",
            "uvicorn",
            "reader.app:create_app",
            "--factory",
            "--port",
            str(api_port),
        ],
        cwd=REPO_ROOT,
    )

    web_proc: subprocess.Popen | None = None
    if not _http_ok(WEB_URL):
        env = {**os.environ, "PATH": f"/opt/homebrew/opt/node/bin:{os.environ.get('PATH', '')}"}
        web_proc = subprocess.Popen(
            ["pnpm", "dev", "--", "--port", str(WEB_PORT), "--strictPort"],
            cwd=WEB_DIR,
            env=env,
        )

    try:
        assert _wait_for(f"{api_url}/api/health", 90), f"API never became healthy on :{api_port}"
        assert _wait_for(WEB_URL, 60), f"Vite dev server never came up on :{WEB_PORT}"
        yield {"api": api_url, "web": WEB_URL}
    finally:
        if web_proc is not None:
            _terminate(web_proc)
        _terminate(api_proc)


@pytest.fixture
def visit_app(page, app_servers):
    """Navigate to the running app, transparently rewiring `/api/**` to the real API port."""
    api_url = app_servers["api"]
    web_url = app_servers["web"]

    def _rewrite(route):
        target = route.request.url.replace(web_url, api_url, 1)
        route.continue_(url=target)

    page.route(f"{web_url}/api/**", _rewrite)

    def _visit() -> None:
        if not page.url.startswith(web_url):
            page.goto(web_url)

    return _visit


@pytest.fixture
def drop_file(page, visit_app):
    """`drop_file({"name", "mimeType", "buffer"})` delivers a file to the drop zone's
    hidden file input -- functionally identical to a real drag-and-drop for the
    app, which only ever sees `onChange`/`onDrop` handing it a `File`."""

    def _drop(file: dict) -> None:
        visit_app()
        page.locator('[data-testid="drop-zone"] input[type="file"]').set_input_files(files=[file])

    return _drop


@pytest.fixture
def word_locator(page):
    """`word_locator("Four")` finds the karaoke span for exactly that word (not a substring)."""

    def _locate(word: str):
        return page.locator(".karaoke-word", has_text=re.compile(rf"^{re.escape(word)}\s*$"))

    return _locate


@pytest.fixture
def state() -> dict:
    """A scratch dict, fresh per scenario, that step definitions stash things in
    (the narration response captured off the wire, and so on).
    """
    return {}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Screenshots this suite deliberately does not keep, keyed by scenario title.
# A value of `None` suppresses every shot the scenario would take; a set of
# names suppresses only those.
#
# - The two error-path scenarios below are tagged @docs only because that
#   marker selects "runs in a real browser", not "needs a documentation
#   image" -- their UI state is identical to the existing rejection
#   screenshot, so a shot here would just be a same-looking duplicate.
# - The other three all reach the shared "I drop it onto the drop zone" step
#   (`_drop_it`), which shoots "01-empty" before the file lands. That shot is
#   byte-identical across every scenario that reuses the step -- same empty
#   drop zone, every time -- and only "Dropping a one-page PDF reveals its
#   text" is the one docs/ actually references (see ADR 0004 and
#   tests/docs/test_generated_images.py, which fails the build if this ever
#   drifts). Suppressing just "01-empty" here still leaves each scenario's
#   own later shot (02-rejected, 02-no-text, ...) intact.
_SUPPRESSED_SHOTS: dict[str, frozenset[str] | None] = {
    "A password-protected PDF says it is locked, not that it is broken": None,
    "A corrupt file named .pdf is reported once, clearly": None,
    "A PDF with no readable text says so instead of going blank": frozenset({"01-empty"}),
    "A non-PDF file is rejected without breaking the page": frozenset({"01-empty"}),
    "A one-page PDF shows no page controls at all": frozenset({"01-empty"}),
}


def pytest_collection_modifyitems(items: list) -> None:
    """Fail collection loudly if `_SUPPRESSED_SHOTS` names a scenario that no
    longer exists (e.g. renamed or removed in a .feature file) -- a stale
    entry would otherwise just silently stop suppressing anything, which is
    exactly the kind of orphan/duplicate screenshot this mechanism exists to
    prevent.
    """
    known = {
        item.obj.__scenario__.name
        for item in items
        if getattr(item.obj, "__scenario__", None) is not None
    }
    stale = set(_SUPPRESSED_SHOTS) - known
    if stale:
        raise pytest.UsageError(
            f"_SUPPRESSED_SHOTS in tests/bdd/conftest.py names scenario(s) that "
            f"don't exist: {sorted(stale)}"
        )


@pytest.fixture
def shot(request, page):
    """`shot(name)` screenshots the app to docs/assets/generated/<scenario-slug>/<name>.png.

    The scenario slug is derived from the pytest-bdd scenario name (set as the
    node's ``obj.__scenario__.name`` by pytest-bdd) so it always matches the
    ADR 0004 convention without each step having to spell it out.

    Screenshots the ``main.app`` container rather than the full page: the
    content column is centered and only as tall as its content (see
    ``browser_context_args`` above), so a full-page screenshot at the fixed
    1280x900 viewport is mostly dead cream margin on every side. Cropping to
    the container keeps every generated image tight around the actual UI.

    Shots (or whole scenarios) listed in `_SUPPRESSED_SHOTS` are skipped --
    see comment above.
    """
    scenario_obj = getattr(request.node.obj, "__scenario__", None)
    scenario_name = scenario_obj.name if scenario_obj is not None else request.node.name

    suppressed = _SUPPRESSED_SHOTS.get(scenario_name, frozenset())
    if suppressed is None:
        return lambda name: None

    directory = SCREENSHOT_ROOT / _slugify(scenario_name)

    def _take(name: str) -> Path | None:
        # mkdir here, not above: a scenario whose every actual shot() call
        # is suppressed (e.g. only "01-empty", which it never gets past)
        # must not leave a directory with nothing in it.
        if name in suppressed:
            return None
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.png"
        page.locator("main.app").screenshot(path=str(path))
        return path

    return _take


@given(parsers.parse('a PDF containing the text "{text}"'), target_fixture="dropped_file")
def _a_pdf_containing_the_text(text: str) -> dict:
    return {"name": "sample.pdf", "mimeType": "application/pdf", "buffer": render(text)}


@then("the page shows the words:")
def _the_page_shows_the_words(word_locator, datatable):
    """Shared by upload.feature and karaoke.feature -- both assert words land on the page."""
    for row in datatable:
        expect(word_locator(row[0])).to_be_visible(timeout=15000)


@when("I drop it onto the drop zone")
def _drop_it(visit_app, shot, drop_file, dropped_file):
    """Shared by upload.feature and karaoke.feature -- both drop a file and check the result."""
    visit_app()
    shot("01-empty")
    drop_file(dropped_file)
