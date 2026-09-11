"""Drift tests for .socraticode.json and the two SocratiCode namespace guards.

`.socraticode.json` is what makes this repo's Qdrant collections addressable by
name instead of by a hash of wherever the working tree happens to sit. Without
it the project id is sha256(abs_path)[:12], so every git worktree is a separate
project with its own six collections and its own full first index — and a
sibling repo linked for cross-repo search resolves to a collection that depends
on the linking host's directory layout.

The guards below are the NOTIFIER_BIND_HOST rule applied to the shared store:
both variables widen or fragment the cohort's namespace while every health
check stays green. See docs/plans/2026-09-11-shared-qdrant-vm-design.md, D0/D12.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / ".socraticode.json"

#: Upstream's own validator: config.js assertValidProjectId rejects anything else.
PROJECT_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

#: Set, and the cohort's collections split in a way nothing reports: the prefix
#: is prepended to the instance-global socraticode_metadata collection as well
#: as the per-project ones.
COLLECTION_PREFIX = "QDRANT_COLLECTION_PREFIX"

#: "true", and the project id gains a branch suffix — a fresh six-collection
#: set per branch, re-indexed from empty on every new branch.
BRANCH_AWARE = "SOCRATICODE_BRANCH_AWARE"

#: Everywhere a variable could reach the MCP server's environment on this host.
NAMESPACE_GUARD_FILES = [
    Path("/etc/notifier/.env"),
    REPO_ROOT / ".env",
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
    REPO_ROOT / "deploy" / "notifier.service",
    REPO_ROOT / "deploy" / "notifier-dev.service",
]


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG.read_text())


def test_config_exists_and_parses():
    """A malformed file is silently ignored by upstream, not reported.

    loadSocratiCodeConfig catches every parse error and returns null, so a typo
    here degrades to the path-hash id with no message — the same silence class
    as the linked-project skip.
    """
    assert CONFIG.exists(), f"{CONFIG.name} is missing"
    json.loads(CONFIG.read_text())


def test_project_id_is_the_repo_name(config):
    """`notifier`, so the collections read as codebase_notifier in a shared store."""
    assert config["projectId"] == "notifier"


def test_project_id_is_qdrant_safe(config):
    """Upstream throws on anything outside [a-zA-Z0-9_-]+ rather than sanitizing."""
    assert set(config["projectId"]) <= PROJECT_ID_CHARS


def test_linked_projects_are_relative(config):
    """Absolute paths are the defect this whole design replaces (#57).

    Relative entries resolve against the repo root, so the same committed file
    works on every cohort VM. A sibling that is not cloned locally is skipped
    silently by upstream — acceptable only because it degrades to searching
    less, and because the health hook reports configured-vs-resolved.
    """
    linked = config["linkedProjects"]
    assert linked, "linkedProjects is empty"
    for entry in linked:
        assert not Path(entry).is_absolute(), f"{entry} is absolute"
        assert entry.startswith("../"), f"{entry} does not name a sibling checkout"


def test_linked_projects_name_the_cohort(config):
    assert set(config["linkedProjects"]) == {
        "../archiver",
        "../broker",
        "../replicator",
        "../watcher",
    }


def test_linked_projects_exclude_this_repo(config):
    """Upstream drops a self-link, but a self-link in the file is still a mistake."""
    assert f"../{REPO_ROOT.name}" not in config["linkedProjects"]


@pytest.mark.parametrize("path", NAMESPACE_GUARD_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("variable", [COLLECTION_PREFIX, BRANCH_AWARE])
def test_namespace_guards_are_not_set_anywhere(variable: str, path: Path):
    """VM-local where the file is VM-local; skips loudly rather than passing vacuously."""
    if not path.exists():
        pytest.skip(f"{path} not present on this machine")
    assert variable not in path.read_text(), f"{path.name} sets {variable}"
