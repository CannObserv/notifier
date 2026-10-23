"""Every skill under ``skills/`` is a whole-directory vendor link unless declared a fork.

A forked ``SKILL.md`` drifts behind upstream on every submodule bump and has to
be 3-way merged back by hand; ``brainstorming`` needed that twice before it
became a link, its local preferences moved to AGENTS.md (#133). A new
fork has to be added here on purpose, with its override notes in docs/SKILLS.md.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERRIDES = {"shipping-work-python-fastapi"}


def _real_skill_dirs(root: str) -> set[str]:
    """Skill names under ``root`` that are real directories: a path nested under one."""
    indexed = subprocess.run(
        ("git", "ls-files", "-z", root),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    depth = root.count("/") + 1
    return {path.split("/")[depth - 1] for path in indexed if path.count("/") > depth - 1}


def test_skills_are_links_except_declared_overrides():
    forks = _real_skill_dirs("skills/")
    assert forks == OVERRIDES, "a skill directory that is not a symlink is a fork; see #133"


def test_claude_skills_holds_links_only():
    """An override belongs in skills/, where the line above sees it, never here."""
    assert not _real_skill_dirs(".claude/skills/")
