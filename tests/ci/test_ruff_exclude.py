"""Drift test for ``[tool.ruff] extend-exclude`` against committed file symlinks.

ruff does not descend into symlinked directories, but it does read a symlinked
*file* with an extension it handles — and ruff 0.16 handles Markdown. The file
symlinks ``managing-skills`` creates point into ``skills-vendor/``, so they
dangle in every CI job (no submodules): ``ruff format --check .`` exits 2 on a
Markdown link, and ``ruff check .`` exits 1 (E902) on a ``pyproject.toml`` one.
Locally the submodules are checked out, the link resolves, and ruff passes, so
nothing short of CI on main noticed the second one (#45, #124).

This reads the git index rather than the working tree, so it fails the same
way with or without submodules — in pytest, ahead of the push.
"""

import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# What ruff 0.16 discovers on its own under `ruff check .` / `format .`:
# `file_resolver.include` in `ruff check --show-settings`, by suffix and by name.
RUFF_SUFFIXES = {".py", ".pyi", ".ipynb", ".md"}
RUFF_NAMES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}


def _committed_symlinks() -> list[str]:
    """Paths git records with mode 120000."""
    result = subprocess.run(
        ("git", "ls-files", "-s", "-z"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        entry.split("\t", 1)[1]
        for entry in result.stdout.split("\0")
        if entry.startswith("120000 ")
    ]


def _ruff_reads(path: str) -> bool:
    """Whether ruff's default include picks up this path."""
    p = Path(path)
    return p.suffix in RUFF_SUFFIXES or p.name in RUFF_NAMES


def _is_excluded(path: str, excludes: list[str]) -> bool:
    """Literal path or directory-prefix match; a glob entry is not modelled."""
    for entry in excludes:
        stem = entry.rstrip("/")
        if path == stem or path.startswith(stem + "/"):
            return True
    return False


def test_every_ruff_readable_file_symlink_is_excluded():
    """A new file symlink must be named in extend-exclude before it reaches CI."""
    excludes = tomllib.loads(PYPROJECT.read_text())["tool"]["ruff"]["extend-exclude"]
    unexcluded = [
        path
        for path in _committed_symlinks()
        if _ruff_reads(path) and not _is_excluded(path, excludes)
    ]
    assert not unexcluded, (
        f"file symlinks ruff will read and that dangle in CI: {unexcluded}; "
        "add each to [tool.ruff] extend-exclude in pyproject.toml (#124)"
    )
