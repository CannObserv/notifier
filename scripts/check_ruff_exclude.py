"""Refuse committed file symlinks that ruff reads but ``extend-exclude`` misses.

The file symlinks ``managing-skills`` creates point into ``skills-vendor/``.
They resolve locally, where the submodules are checked out, and dangle in CI,
which checks out without them — so a local ruff run passes and CI's ``lint``
goes red on main (#45, #124). This reads the git index rather than the working
tree, so it fails the same way with or without submodules.

Stdlib only and no database: it runs as a ``pre-commit`` hook, where pytest
cannot (``tests/conftest.py`` needs ``TEST_DATABASE_URL``), and
``tests/ci/test_ruff_exclude.py`` runs it again in CI (#126).

Run from the repo root: ``uv run python scripts/check_ruff_exclude.py``.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

# What ruff 0.16 discovers on its own under `ruff check .` / `format .`:
# `file_resolver.include` in `ruff check --show-settings`, by suffix and by name.
# tests/ci/test_ruff_exclude.py holds these to that output, extend-include too.
RUFF_SUFFIXES = {".py", ".pyi", ".ipynb", ".md"}
RUFF_NAMES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, capture_output=True, text=True, check=True
    ).stdout


def _committed_symlinks(root: Path) -> list[str]:
    """Paths the index records with mode 120000."""
    return [
        entry.split("\t", 1)[1]
        for entry in _git(root, "ls-files", "-s", "-z").split("\0")
        if entry.startswith("120000 ")
    ]


def _ruff_reads(path: str) -> bool:
    """Whether ruff's default include picks up this path."""
    p = Path(path)
    return p.suffix in RUFF_SUFFIXES or p.name in RUFF_NAMES


def is_excluded(path: str, excludes: list[str]) -> bool:
    """Literal path or directory-prefix match; a glob entry is not modelled."""
    for entry in excludes:
        stem = entry.rstrip("/")
        if path == stem or path.startswith(stem + "/"):
            return True
    return False


def unexcluded_symlinks(root: Path) -> list[str]:
    """Indexed file symlinks under ``root`` that ruff reads and does not exclude."""
    config = tomllib.loads((root / "pyproject.toml").read_text())
    excludes = config.get("tool", {}).get("ruff", {}).get("extend-exclude", [])
    return [
        path
        for path in _committed_symlinks(root)
        if _ruff_reads(path) and not is_excluded(path, excludes)
    ]


def main() -> int:
    """Check the repository containing the working directory; 1 on a miss."""
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    unexcluded = unexcluded_symlinks(root)
    for path in unexcluded:
        print(
            f"{path}: file symlink ruff reads, dangles in CI (no submodules); "
            "add it to [tool.ruff] extend-exclude in pyproject.toml (#124)",
            file=sys.stderr,
        )
    return 1 if unexcluded else 0


if __name__ == "__main__":
    sys.exit(main())
