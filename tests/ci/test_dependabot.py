"""Drift tests for .github/dependabot.yml — the mechanism behind the cap policy.

The 0.x cap policy (#30) converts "the resolver picks it up" into "a person
decides": every minor bump on a capped dependency needs a hand edit. Dependabot
is what proposes those edits (#33), and its config fails completely silently —
a deleted or mistyped file just stops producing PRs, and the first symptom is
a security fix sitting unnoticed behind a cap.

The conditions asserted here are the ones a reader cannot check by eye:

* **The uv blocks must cover every dependency table.** The expected directory
  set is derived from ``TABLES`` in ``test_dependencies.py``, so a table added
  there without a matching dependabot directory fails here rather than
  drifting.
* **The versioning strategy must be pinned to ``increase-if-necessary``.**
  The default ``auto`` resolves to ``widen`` for libraries — the SDK
  classifies as one — and ``widen`` is unsupported for uv
  (dependabot-core#15290), so the default is broken for ``/clients/python``.
  The pin does not keep floors still under uv: #52–#54 raised them on
  in-range bumps anyway (#103), so an SDK PR's floor is checked by hand.
* **The open-PR limit must exceed what one backlog can fill.** Dependabot
  defaults ``open-pull-requests-limit`` to 5 per block and then opens nothing
  — no error, no notice. #51–#55 filled it, and the dev-tools group and the
  SDK table went silent for five weeks (#103).
* **The workflows' actions are covered too.** They drift the same way and are
  gated the same way (by themselves, on the bump PR).
"""

import tomllib
from pathlib import Path

import pytest
import yaml

from tests.ci.test_dependencies import REPO_ROOT, TABLES

CONFIG = REPO_ROOT / ".github" / "dependabot.yml"


def dependabot_directory(table: Path) -> str:
    """A dependency table's directory, in dependabot's shape (`/`, `/clients/python`)."""
    return (
        "/" if table.parent == REPO_ROOT else f"/{table.parent.relative_to(REPO_ROOT).as_posix()}"
    )


def expected_directories() -> set[str]:
    """One dependabot directory per dependency table."""
    return {dependabot_directory(path) for path in TABLES.values()}


def load() -> dict:
    """The parsed config, or an empty document while the file is missing.

    Tolerating absence keeps collection alive so the failure surfaces as
    ``test_config_exists``'s message rather than a collection error.
    """
    return yaml.safe_load(CONFIG.read_text()) if CONFIG.is_file() else {}


def blocks(ecosystem: str) -> list[dict]:
    return [u for u in load().get("updates", []) if u["package-ecosystem"] == ecosystem]


def directories(block: dict) -> set[str]:
    """A block's directories, whichever of the two spellings it uses."""
    return set(block.get("directories", [])) | (
        {block["directory"]} if "directory" in block else set()
    )


def test_config_exists():
    assert CONFIG.is_file(), (
        "no .github/dependabot.yml — nothing proposes the bumps the 0.x cap "
        "policy makes invisible to `uv lock` (#33)"
    )


def test_config_is_version_2():
    """Version 1 configs are dead; dependabot ignores them without erroring."""
    assert load().get("version") == 2


def test_uv_blocks_cover_every_dependency_table():
    covered = set().union(*(directories(block) for block in blocks("uv")))
    missing = expected_directories() - covered
    assert not missing, (
        f"tables at {sorted(missing)} get no bump PRs — their caps drift "
        f"silently. Add the directory to the uv update block."
    )


@pytest.mark.parametrize("block", blocks("uv"), ids=lambda b: ",".join(sorted(directories(b))))
def test_uv_strategy_is_not_the_unsupported_widen(block):
    """The default `auto` tries `widen` for the SDK, which uv does not support
    (dependabot-core#15290). It is not a floor guard: under uv, in-range bumps
    still raised floors (#52–#54)."""
    assert block.get("versioning-strategy") == "increase-if-necessary"


@pytest.mark.parametrize("block", blocks("uv"), ids=lambda b: ",".join(sorted(directories(b))))
def test_uv_dev_churn_is_grouped(block):
    """Eight separate PRs a week is how a bot gets muted (#33). Dev-group
    tools carry most of the churn; runtime deps stay individual PRs."""
    groups = block.get("groups", {})
    assert any(group.get("dependency-type") == "development" for group in groups.values()), (
        "no group collapses development dependencies; ruff alone would open a PR most months"
    )


def test_actions_are_covered_too():
    covered = set().union(*(directories(block) for block in blocks("github-actions")))
    assert "/" in covered, (
        ".github/workflows/ pins actions/checkout and astral-sh/setup-uv; "
        "they drift exactly like the uv tables"
    )


@pytest.mark.parametrize("ecosystem", ["uv", "github-actions"], ids=str)
def test_every_block_runs_on_a_schedule(ecosystem):
    """A block without an interval is a config dependabot rejects — visibly
    only in the repo's Dependabot tab, which nobody watches."""
    for block in blocks(ecosystem):
        assert block.get("schedule", {}).get("interval"), (
            f"{ecosystem} block declares no schedule.interval"
        )


def table_for(directory: str) -> Path:
    """The pyproject.toml a dependabot directory names."""
    return next(path for path in TABLES.values() if dependabot_directory(path) == directory)


@pytest.mark.parametrize("block", blocks("uv"), ids=lambda b: ",".join(sorted(directories(b))))
def test_uv_open_pr_limit_outlasts_a_full_backlog(block):
    """Every runtime dependency is its own PR and every group one more per
    directory. If that many can be open at once and the limit is lower, the
    bot stops proposing anything — the cap policy's one escape hatch, shut
    without a sign (#103)."""
    runtime = sum(
        len(tomllib.loads(table_for(d).read_text())["project"]["dependencies"])
        for d in directories(block)
    )
    grouped = len(block.get("groups", {})) * len(directories(block))
    limit = block.get("open-pull-requests-limit", 5)
    assert limit > runtime + grouped, (
        f"limit {limit} can be filled by {runtime} runtime PRs and {grouped} group PRs; "
        f"raise open-pull-requests-limit"
    )
