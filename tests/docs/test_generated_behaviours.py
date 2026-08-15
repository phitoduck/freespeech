"""Catches drift between docs/reference/behaviours.md and the feature files
it's generated from. This is the exact failure ADR 0004 exists to prevent,
observed directly: a scenario in features/karaoke.feature was edited and the
rendered page kept showing the old wording for over half an hour, because
`mkdocs build --strict` checks links, not generator freshness, and only
`make docs` (not a bare `mkdocs build`) regenerates the page first. Pure
filesystem + regex -- no browser, no model, no servers -- so this is
unmarked and runs in the normal fast suite, not under `-m docs`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.gen_behaviours import OUT, render

ROOT = Path(__file__).resolve().parents[2]


def test_behaviours_page_matches_feature_files():
    """docs/reference/behaviours.md must equal render() of the current
    features/*.feature -- if it doesn't, someone edited a .feature file (or
    the page itself) without regenerating.
    """
    features = sorted((ROOT / "features").glob("*.feature"))
    assert OUT.read_text() == render(features), (
        f"{OUT.relative_to(ROOT)} is stale: it doesn't match the current "
        "features/*.feature. Run `uv run python scripts/gen_behaviours.py` "
        "(or `make docs`) and commit the result."
    )


def test_unrecognised_flag_is_refused_and_does_not_rewrite():
    """An unknown flag must be refused loudly, not silently ignored.

    Example: `gen_behaviours.py --check` -- expected a dry-run that verifies
    freshness (non-zero exit, file untouched if stale). Today `main()` never
    looks at sys.argv, so the flag is ignored and the page is rewritten
    anyway, printing "wrote ..." with exit 0 -- a staleness gate built on
    this can never fail.
    """
    before = OUT.read_bytes()
    try:
        result = subprocess.run(
            [sys.executable, "scripts/gen_behaviours.py", "--check"],
            cwd=ROOT,
            capture_output=True,
        )
        assert result.returncode != 0
        assert OUT.read_bytes() == before
    finally:
        if OUT.read_bytes() != before:
            OUT.write_bytes(before)
