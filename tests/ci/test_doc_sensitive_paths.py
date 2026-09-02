"""Drift tests for ``.skills/doc-sensitive-paths``.

``shipping-work-python-fastapi``'s Step 1.5 gate (``doc-check.sh``) flags
branch changes that touch files the docs describe. Its built-in defaults are
written for a generic FastAPI service; this repo replaces them wholesale with
a committed list, because three defaults (``schema.sql``, ``src/models/``,
``.env.example``) name nothing that exists here, and four surfaces the docs
do describe were missing — ``scripts/``, ``.github/workflows/``, ``skills/``
and, since the review of #47, ``skills-vendor/`` and ``.skills/``.

Replacing the defaults moves their upkeep here, and a sensitive-path list
fails the same way the bug upstream fixed did (gregoryfoster/skills#252): an
entry that matches no tracked file contributes nothing, and its silence is
byte-identical to a genuinely doc-neutral branch. ``doc-check.sh`` catches
only the all-dead case at ship time, and it exits 2 there rather than naming
the one entry that rotted. This test catches a single dead entry, in CI, on
the commit that kills it — a directory renamed or a file deleted narrows the
gate silently otherwise.

The matcher is a transcription of ``path_matches()`` in ``doc-check.sh``,
and nothing here asserts the two still agree — a divergence would be worth
failing on, but this file does not catch one. Re-read both when either
moves. Transcribing rather than shelling out to the script is deliberate:
these entries are checked against the tracked tree, which needs no base ref
and so returns the same verdict on a branch with nothing to diff.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PATH_LIST = REPO_ROOT / ".skills" / "doc-sensitive-paths"


def _entries() -> list[str]:
    """Parse the path list the way ``doc-check.sh`` does."""
    lines = PATH_LIST.read_text().splitlines()
    return [
        stripped
        for stripped in (line.strip() for line in lines)
        if stripped and not stripped.startswith("#")
    ]


def _tracked() -> list[str]:
    result = subprocess.run(
        ("git", "-c", "core.quotePath=false", "ls-files"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def _matches(file: str, entry: str) -> bool:
    """Segment match, mirroring ``path_matches()`` in ``doc-check.sh``."""
    if entry.endswith("/"):
        return file.startswith(entry) or f"/{entry}" in file
    return (
        file == entry
        or file.endswith(f"/{entry}")
        or file.startswith(f"{entry}/")
        or f"/{entry}/" in file
    )


ENTRIES = _entries() if PATH_LIST.exists() else []
# One snapshot for the module: every entry is then judged against the same
# tree, and the check costs one subprocess rather than one per entry.
TRACKED = _tracked()


def test_path_list_is_committed() -> None:
    """The list replaces the defaults, so it has to exist and name something."""
    assert PATH_LIST.exists(), f"{PATH_LIST} is missing; doc-check.sh would fall back to defaults"
    assert ENTRIES, "the list parses to no entries; doc-check.sh exits 2 on that"


@pytest.mark.parametrize("entry", ENTRIES)
def test_entry_matches_a_tracked_file(entry: str) -> None:
    """A dead entry narrows the gate without narrowing what it reports."""
    assert any(_matches(file, entry) for file in TRACKED), (
        f"{entry!r} matches no tracked file, so it can never flag a change. "
        "Drop it from .skills/doc-sensitive-paths or fix the path."
    )
