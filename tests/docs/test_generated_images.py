"""Mechanical checks on docs/assets/generated/, the screenshot output ADR
0004 (docs/explanation/adr/0004-documentation-images-are-test-output.md)
calls a documentation artefact. Pure filesystem + regex -- no browser, no
model, no servers -- so this is unmarked and runs in the normal fast suite,
not under `-m docs`.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
GENERATED = DOCS / "assets" / "generated"

# Matches markdown image syntax and captures the path inside the parens,
# e.g. "![alt text](../assets/generated/x/01-empty.png)" -> the path.
_IMAGE_REF = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


def _referenced_generated_images() -> set[Path]:
    """Every docs/assets/generated/ file that some .md page under docs/
    actually links to, resolved from the *relative path as written* (never
    basename) so same-named files under different scenario slugs don't get
    confused for one another -- that basename confusion is the exact bug
    this test exists to catch (see ADR 0004).

    >>> refs = _referenced_generated_images()
    >>> (GENERATED / "karaoke" / "karaoke.gif") in refs
    True
    """
    referenced: set[Path] = set()
    for md_file in DOCS.rglob("*.md"):
        for match in _IMAGE_REF.finditer(md_file.read_text()):
            target = (md_file.parent / match.group(1)).resolve()
            if target == GENERATED or GENERATED in target.parents:
                referenced.add(target)
    return referenced


def _generated_files() -> list[Path]:
    return [p.resolve() for p in GENERATED.rglob("*") if p.is_file()]


def test_no_orphaned_generated_images():
    """Every file under docs/assets/generated/ must be linked from some
    page under docs/, by its full relative path. An ad-hoc basename-only
    check previously reported zero orphans while three duplicate
    01-empty.png files (one per scenario slug) sat unreferenced -- this
    replaces that check with one that can actually fail.
    """
    referenced = _referenced_generated_images()
    orphans = sorted(p for p in _generated_files() if p not in referenced)
    assert not orphans, (
        "Orphaned files under docs/assets/generated/ -- reference them from "
        "a .md file under docs/ or delete them:\n"
        + "\n".join(f"  {p.relative_to(DOCS)}" for p in orphans)
    )


def test_no_duplicate_generated_images():
    """No two files under docs/assets/generated/ may be byte-identical. A
    shared BDD step (e.g. the one screenshotting the empty drop zone) can
    write the same image under several scenario slugs; only one copy should
    survive -- if a shot is worth keeping, it should be produced once.
    """
    by_md5: dict[str, list[Path]] = {}
    for path in _generated_files():
        by_md5.setdefault(hashlib.md5(path.read_bytes()).hexdigest(), []).append(path)

    duplicates = {digest: paths for digest, paths in by_md5.items() if len(paths) > 1}
    assert not duplicates, "Byte-identical files under docs/assets/generated/:\n" + "\n".join(
        f"  {digest}: {', '.join(str(p.relative_to(DOCS)) for p in sorted(paths))}"
        for digest, paths in duplicates.items()
    )
