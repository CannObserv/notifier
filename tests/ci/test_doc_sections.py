"""Drift tests for ``.skills/doc-sections``.

``shipping-work-python-fastapi``'s Step 1.5 gate prints two tailorable lists.
``.skills/doc-sensitive-paths`` says what the gate watches;
``.skills/doc-sections`` is the advice printed on a hit — which docs to
spot-check. Each replaces its built-in defaults wholesale, and since
gregoryfoster/skills#284 a hit whose repo tailored only one of the two ends
with a note naming the half that is still generic. This repo tailored the
path list in #47 and the sections in #65, so both halves are its own.

Upstream runs no dead-entry check on the sections, because upstream's are
prose and prose names nothing checkable. This repo's are not prose: every
line opens with a doc path and closes with the sensitive paths it routes,
which makes both halves falsifiable. Two ways they rot, neither visible at
ship time:

* A doc named here is renamed or deleted. The advice then sends the reader
  at a path that does not exist, and ``doc-check.sh`` prints it as
  confidently as any other line.
* A path is added to ``.skills/doc-sensitive-paths`` and nothing here routes
  it. The gate flags the change and the advice says nothing about it, which
  is the failure gregoryfoster/skills#261 describes: a hit that names no doc
  is a hit the reader waves through.

The entry parser mirrors ``read_list_file()`` in ``doc-check.sh``; the
``<doc>: <advice>`` shape is this repo's convention on top of it, not the
script's, so nothing upstream enforces it and this file is the only gate.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SECTIONS = REPO_ROOT / ".skills" / "doc-sections"
PATH_LIST = REPO_ROOT / ".skills" / "doc-sensitive-paths"


def _entries(path: Path) -> list[str]:
    """Parse a ``.skills/`` list the way ``doc-check.sh`` does."""
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [
        stripped
        for stripped in (line.strip() for line in lines)
        if stripped and not stripped.startswith("#")
    ]


def _tracked() -> set[str]:
    result = subprocess.run(
        ("git", "-c", "core.quotePath=false", "ls-files"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return set(result.stdout.splitlines())


SECTION_ENTRIES = _entries(SECTIONS)
PATH_ENTRIES = _entries(PATH_LIST)
TRACKED = _tracked()


def test_sections_are_committed() -> None:
    """Absent, the gate prints defaults written for a layout that is not ours."""
    assert SECTIONS.exists(), (
        f"{SECTIONS} is missing; doc-check.sh would print its built-in sections "
        "and, because .skills/doc-sensitive-paths is tailored, a half-tailoring note"
    )
    assert SECTION_ENTRIES, "the file parses to no sections; doc-check.sh exits 2 on that"


@pytest.mark.parametrize("entry", SECTION_ENTRIES)
def test_entry_names_a_tracked_doc(entry: str) -> None:
    """Advice pointing at a renamed doc sends the reader nowhere."""
    doc, sep, _ = entry.partition(": ")
    assert sep, f"{entry!r} does not open with '<doc path>: '; see this file's docstring"
    assert doc in TRACKED, (
        f"{doc!r} is not a tracked file, so this line routes a hit at a doc that is "
        "gone. Repoint it or drop the line from .skills/doc-sections."
    )


@pytest.mark.parametrize("path_entry", PATH_ENTRIES)
def test_every_sensitive_path_is_routed(path_entry: str) -> None:
    """A watched surface no line names is a hit with no advice attached."""
    # Boundary-guarded so `skills/` is not credited to `.skills/`, which
    # contains it, and `deploy/` is not credited to a `redeploy/` if one
    # ever lands. Anything alphanumeric or `.`/`-`/`/` before the entry
    # means a longer path, not this one.
    pattern = re.compile(rf"(?<![\w./-]){re.escape(path_entry)}")
    assert any(pattern.search(entry) for entry in SECTION_ENTRIES), (
        f"{path_entry!r} is watched by .skills/doc-sensitive-paths but no line in "
        ".skills/doc-sections names it, so a hit on it prints advice that never "
        "says which doc describes it."
    )
