"""Drift test for ``[tool.ruff] extend-exclude`` against committed file symlinks.

ruff does not descend into symlinked directories, but it does read a symlinked
*file* with an extension it handles — and ruff 0.16 handles Markdown. The file
symlinks ``managing-skills`` creates point into ``skills-vendor/``, so they
dangle in every CI job (no submodules): ``ruff format --check .`` exits 2 on a
Markdown link, and ``ruff check .`` exits 1 (E902) on a ``pyproject.toml`` one.
Locally the submodules are checked out, the link resolves, and ruff passes, so
nothing short of CI on main noticed the second one (#45, #124).

The check itself is ``scripts/check_ruff_exclude.py``, which reads the git
index and needs no database, so ``pre-commit`` refuses the commit before it
exists (#126). This is the CI half of the same assertion, plus the wiring that
makes the hook fire: a hook that never triggers passes exactly like one that
finds nothing.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

from scripts.check_ruff_exclude import (
    RUFF_NAMES,
    RUFF_SUFFIXES,
    is_excluded,
    unexcluded_symlinks,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"
HOOK_ID = "ruff-exclude-symlinks"
INCLUDE_KEYS = ("file_resolver.include", "file_resolver.extend_include")


def _ruff_include_patterns() -> list[str]:
    """Every pattern in ruff's resolved include and extend-include, as ruff prints them."""
    settings = subprocess.run(
        (sys.executable, "-m", "ruff", "check", "--show-settings"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    patterns: list[str] = []
    lines = iter(settings.splitlines())
    for line in lines:
        key, _, value = line.partition(" = ")
        if key not in INCLUDE_KEYS:
            continue
        if value != "[]":
            for item in lines:
                if item.strip() == "]":
                    break
                patterns.append(item.strip().rstrip(",").strip('"'))
    return patterns


def _hook() -> dict:
    config = yaml.safe_load(PRE_COMMIT.read_text())
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    matches = [hook for hook in hooks if hook["id"] == HOOK_ID]
    assert len(matches) == 1, f"expected one {HOOK_ID!r} hook in {PRE_COMMIT.name}"
    return matches[0]


def test_every_ruff_readable_file_symlink_is_excluded():
    """A new file symlink must be named in extend-exclude before it reaches CI."""
    unexcluded = unexcluded_symlinks(REPO_ROOT)
    assert not unexcluded, (
        f"file symlinks ruff will read and that dangle in CI: {unexcluded}; "
        "add each to [tool.ruff] extend-exclude in pyproject.toml (#124)"
    )


def test_ruff_reads_exactly_what_the_check_models():
    """The check's suffix and name lists are copied from ruff, so hold them to it.

    This is how the class began: ruff 0.16 started reading ``*.md``, and a
    Markdown link turned main red (#45). A ruff bump or an ``extend-include``
    that widens discovery would otherwise leave the check green on a type it
    never looks at. A pattern of any other shape fails too, since the check
    could not model it.
    """
    suffixes, names, unmodelled = set(), set(), []
    for pattern in _ruff_include_patterns():
        if pattern.startswith("*.") and "/" not in pattern:
            suffixes.add(pattern[1:])
        elif pattern.startswith("**/") and "*" not in pattern[3:]:
            names.add(pattern[3:])
        else:
            unmodelled.append(pattern)
    assert not unmodelled, f"ruff include patterns the check cannot model: {unmodelled}"
    assert suffixes == RUFF_SUFFIXES, "update RUFF_SUFFIXES in scripts/check_ruff_exclude.py"
    assert names == RUFF_NAMES, "update RUFF_NAMES in scripts/check_ruff_exclude.py"


def test_pre_commit_hook_runs_the_check():
    hook = _hook()
    assert "scripts/check_ruff_exclude.py" in hook["entry"]
    assert hook.get("pass_filenames") is False, "the check reads the whole index"


def test_pre_commit_hook_fires_on_new_links_and_pyproject():
    """Both halves of the failure: a link is added, or its exclude is removed.

    ``types_or`` rather than ``files``: a link's name is arbitrary, and
    pre-commit ANDs ``files`` with the tag filters, so only tags can OR the
    two. ``symlink`` is the tag a staged link carries; ``toml`` is
    pyproject.toml's. ``types`` must be spelled empty: its default is
    ``[file]``, which a link's tags (``{symlink}`` alone) never satisfy, so
    the default skips every link with "(no files to check)".
    """
    hook = _hook()
    assert {"symlink", "toml"} <= set(hook.get("types_or", []))
    assert hook.get("types") == [], "the default types: [file] drops every symlink"
    assert "files" not in hook, "files is ANDed with types_or and would narrow it"


def test_every_extend_exclude_entry_names_an_indexed_path():
    """An exclude whose path left the index guards nothing and hides what lands there.

    The two ``skills/brainstorming/`` file entries outlived the override they
    were added for (#133); a stale entry also reads as a live constraint.
    """
    excludes = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["tool"]["ruff"][
        "extend-exclude"
    ]
    indexed = subprocess.run(
        ("git", "ls-files", "-z"), cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    globs = [entry for entry in excludes if any(c in entry for c in "*?[")]
    assert not globs, f"is_excluded matches literal paths only, so cannot check: {globs}"
    stale = [entry for entry in excludes if not any(is_excluded(p, [entry]) for p in indexed)]
    assert not stale, f"[tool.ruff] extend-exclude entries matching nothing in the index: {stale}"
