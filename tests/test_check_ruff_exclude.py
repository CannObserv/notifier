"""Tests for scripts/check_ruff_exclude.py, against throwaway git repos.

Each repo is built from scratch so the check's input is exactly what the test
says it is — the real index carries whatever links happen to be committed.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_ruff_exclude import unexcluded_symlinks

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_ruff_exclude.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _pyproject(repo: Path, excludes: list[str]) -> None:
    entries = ", ".join(f'"{e}"' for e in excludes)
    (repo / "pyproject.toml").write_text(f"[tool.ruff]\nextend-exclude = [{entries}]\n")


def _stage_link(repo: Path, path: str) -> None:
    """Stage a symlink that dangles, as every vendored link does in CI."""
    link = repo / path
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink("../../skills-vendor/absent/" + link.name, link)
    _git(repo, "add", path)


def test_unexcluded_markdown_link_is_reported(repo):
    _pyproject(repo, [])
    _stage_link(repo, "skills/brainstorming/new.md")
    assert unexcluded_symlinks(repo) == ["skills/brainstorming/new.md"]


def test_link_named_in_extend_exclude_passes(repo):
    _pyproject(repo, ["skills/brainstorming/new.md"])
    _stage_link(repo, "skills/brainstorming/new.md")
    assert unexcluded_symlinks(repo) == []


def test_directory_prefix_exclude_covers_link(repo):
    _pyproject(repo, ["skills/brainstorming/"])
    _stage_link(repo, "skills/brainstorming/new.md")
    assert unexcluded_symlinks(repo) == []


def test_pyproject_link_is_read_by_name(repo):
    """`ruff check .` exits 1 (E902) on a dangling pyproject.toml link."""
    _pyproject(repo, [])
    _stage_link(repo, "skills/foo/pyproject.toml")
    assert unexcluded_symlinks(repo) == ["skills/foo/pyproject.toml"]


def test_link_ruff_does_not_read_is_ignored(repo):
    _pyproject(repo, [])
    _stage_link(repo, "skills/foo/run.sh")
    assert unexcluded_symlinks(repo) == []


def test_unstaged_link_is_not_reported(repo):
    """The index is what gets committed; an untracked link is not yet a risk."""
    _pyproject(repo, [])
    os.symlink("missing.md", repo / "loose.md")
    assert unexcluded_symlinks(repo) == []


def test_script_exits_nonzero_and_names_the_link(repo):
    """The pre-commit hook reads the exit status; the message says what to fix."""
    _pyproject(repo, [])
    _stage_link(repo, "skills/brainstorming/new.md")
    result = subprocess.run((sys.executable, str(SCRIPT)), cwd=repo, capture_output=True, text=True)
    assert result.returncode == 1
    assert "skills/brainstorming/new.md" in result.stderr
    assert "extend-exclude" in result.stderr


def test_script_exits_zero_when_clean(repo):
    _pyproject(repo, ["skills/brainstorming/new.md"])
    _stage_link(repo, "skills/brainstorming/new.md")
    result = subprocess.run((sys.executable, str(SCRIPT)), cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
