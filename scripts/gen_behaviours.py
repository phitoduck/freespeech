"""Turn the Gherkin in ``features/`` into the Reference page for the docs site.

The Reference quadrant describes what the software does. Since the feature files
already say that, and are executed on every test run, generating the page from
them is the only way it cannot drift (ADR 0004).

    $ uv run python scripts/gen_behaviours.py
    wrote docs/reference/behaviours.md (2 features, 23 scenarios)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reference" / "behaviours.md"

_SCENARIO = re.compile(r"^\s*(@[\w @]+\n)?\s*(Scenario|Scenario Outline):", re.MULTILINE)


def count_scenarios(gherkin: str) -> int:
    """Number of scenarios in a feature file's text.

    >>> count_scenarios("Feature: f\\n  @docs\\n  Scenario: a\\n  Scenario: b\\n")
    2
    """
    return len(_SCENARIO.findall(gherkin))


def render(features: list[Path]) -> str:
    """Render feature files as one Markdown page, each in a fenced gherkin block.

    >>> print(render([]).splitlines()[0])
    # Behaviours
    """
    parts = [
        "# Behaviours",
        "",
        "Every behaviour this reader promises, in the language the tests execute.",
        "",
        "Scenarios tagged `@docs` are worked examples and produce the screenshots",
        "elsewhere in this Reference. Scenarios tagged `@property` are universally",
        "quantified — read *any* as *for all* — and run against generated input.",
        "",
        "!!! info \"This page is generated\"",
        "    `uv run python scripts/gen_behaviours.py` rewrites it from",
        "    `features/*.feature`. Edit the feature files, not this page.",
        "",
    ]
    for path in features:
        parts += [f"## `{path.name}`", "", "```gherkin", path.read_text().strip(), "```", ""]
    return "\n".join(parts)


def main() -> None:
    if sys.argv[1:]:
        raise SystemExit(f"gen_behaviours.py takes no arguments, got {sys.argv[1:]}")
    features = sorted((ROOT / "features").glob("*.feature"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(features))
    total = sum(count_scenarios(p.read_text()) for p in features)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(features)} features, {total} scenarios)")


if __name__ == "__main__":
    main()
