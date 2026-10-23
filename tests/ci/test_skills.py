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


def test_skills_are_links_except_declared_overrides():
    """A path nested under skills/<name>/ means that directory is real, not a link."""
    indexed = subprocess.run(
        ("git", "ls-files", "-z", "skills/"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    forks = {path.split("/")[1] for path in indexed if path.count("/") > 1}
    assert forks == OVERRIDES, "a skill directory that is not a symlink is a fork; see #133"
