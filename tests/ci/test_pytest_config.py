"""Drift test for pytest's basetemp retention in ``[tool.pytest.ini_options]``.

The disk GC's alert line on this host is sized from the baseline plus one
test run's basetemp (#136, maintaining-host-disk's ``repo-knobs.md``). pytest
keeps three basetemps by default, failed or not, so a dropped key widens the
swing the line was sized for without failing anything.
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def ini_options() -> dict:
    config = tomllib.loads(PYPROJECT.read_text())
    return config["tool"]["pytest"]["ini_options"]


def test_basetemp_retention_keeps_one_run(ini_options):
    assert ini_options.get("tmp_path_retention_count") == 1, (
        "pytest's default keeps 3 basetemps; the disk GC's alert line assumes 1 (#136)"
    )


def test_basetemp_retention_keeps_failed_runs_only(ini_options):
    assert ini_options.get("tmp_path_retention_policy") == "failed", (
        "a passing run's basetemp has nothing to debug; keep only a failed one's (#136)"
    )
