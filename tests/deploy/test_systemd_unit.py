"""Drift tests for deploy/notifier.service.

The production opt-in flag must live in the unit itself. Anything placed in an
EnvironmentFile is inherited by every process that sources that file, which
re-opens the hole for exactly the hand-run servers the guard targets — and
this unit loads both /etc/notifier/.env and the repo .env.
"""

from pathlib import Path

import pytest

from src.core import db_safety

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT = REPO_ROOT / "deploy" / "notifier.service"


def test_unit_sets_the_production_opt_in_flag():
    body = UNIT.read_text()
    assert f"Environment={db_safety.ALLOW_PROD_ENV_VAR}=1" in body


@pytest.mark.parametrize(
    "env_file", [Path("/etc/notifier/.env"), REPO_ROOT / ".env"], ids=["etc", "repo"]
)
def test_opt_in_flag_is_not_in_any_env_file_on_the_unit_load_path(env_file):
    """VM-local check. Skips loudly off-VM rather than passing vacuously."""
    if not env_file.exists():
        pytest.skip(f"{env_file} not present on this machine")
    assert db_safety.ALLOW_PROD_ENV_VAR not in env_file.read_text(), (
        f"{env_file} is on the unit's EnvironmentFile path and would leak "
        f"the opt-in to every process that sources it"
    )


def test_unit_still_serves_port_9000():
    assert "--port 9000" in UNIT.read_text()
