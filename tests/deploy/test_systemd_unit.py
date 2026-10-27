"""Drift tests for deploy/notifier.service.

The production opt-in flag must live in the unit itself. Anything placed in an
EnvironmentFile is inherited by every process that sources that file, which
re-opens the hole for exactly the hand-run servers the guard targets — and
this unit loads both /etc/notifier/.env and the repo .env.
"""

from pathlib import Path

import pytest

from src.core import db_safety
from tests.deploy.systemd_units import (
    REPO_ROOT,
    directives,
    seconds,
    tailnet_wait_seconds,
    values,
)

UNIT = REPO_ROOT / "deploy" / "notifier.service"
SERVE = REPO_ROOT / "scripts" / "serve.sh"


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


def test_unit_launches_through_the_guarded_script():
    """ExecStart is the launch script, not a uvicorn line.

    The dev unit has made this argument since #24: a second uvicorn spelling is
    a second code path that drifts out from under the guards. #43 gives the
    production unit the same reason. It must resolve this host's tailnet
    address before binding, and systemd reads ``EnvironmentFile=`` *before*
    ``ExecStartPre`` runs — so no ExecStartPre can hand the address to
    ExecStart. Resolving and binding have to happen in one process.
    """
    body = directives(UNIT)
    assert "scripts/serve.sh" in body
    assert "uvicorn" not in body


def test_serve_script_still_serves_port_9000():
    assert "--port 9000" in SERVE.read_text()


def test_serve_script_binds_the_tailnet_address_only():
    """#43 D3 — never 0.0.0.0, which exe.dev's proxy would republish on :9000."""
    body = SERVE.read_text()
    assert "tailnet_bind.sh" in body
    assert "0.0.0.0" not in body


def test_unit_orders_after_tailscaled():
    """Necessary but not sufficient — After= does not wait for an address.

    The wait itself lives in tailnet_bind.sh; this only stops the unit from
    racing tailscaled's *start*, which is the cheap half of observo#473.
    """
    after = [line for line in directives(UNIT).splitlines() if line.startswith("After=")]
    assert after, "unit declares no ordering at all"
    assert any("tailscaled.service" in line for line in after)


def test_unit_bounds_its_restart_loop_around_the_tailnet_wait():
    """Retry long enough to ride out tailscaled, then give up somewhere visible.

    Each failed start now costs the full tailnet wait before RestartSec even
    begins, so the default 10s StartLimitIntervalSec can never trip and a
    genuinely broken config would retry forever — the failure mode the dev
    unit's bound exists to prevent, arriving here by a different route.
    """
    assert seconds(UNIT, "StartLimitBurst") == 5
    assert seconds(UNIT, "StartLimitIntervalSec") == 900
    assert seconds(UNIT, "RestartSec") == 5


def test_unit_start_limit_can_trip_on_its_slowest_crash_loop():
    """The limit must be able to count every start of a loop, tailnet wait and all.

    Under ``Restart=always`` (#143) every exit systemd did not ask for is
    another start, and every start — auto or manual, whatever the exit status
    — counts against the burst. The slowest loop is a start that waits the
    full tailnet bound before failing. If even that one fits inside the
    interval, every faster loop does too.
    """
    burst = seconds(UNIT, "StartLimitBurst")
    worst = burst * (tailnet_wait_seconds() + seconds(UNIT, "RestartSec"))
    assert worst <= seconds(UNIT, "StartLimitIntervalSec"), (
        f"{burst} slow failures take {worst}s, longer than the window that counts "
        "them — the limit never trips and a broken unit retries forever"
    )


def test_unit_restarts_on_any_exit_systemd_did_not_ask_for():
    """#143: a deliberate stop logs as success; any other exit still restarts.

    ``uv run`` exits 143 after a SIGTERM, because uvicorn re-raises the
    signal it caught and uv reports the child's death as 128+15. Without
    ``SuccessExitStatus=143`` every ``systemctl restart`` writes ``Failed with
    result 'exit-code'``, burying a real failure. With it but under
    ``Restart=on-failure``, a SIGTERM systemd did not send — earlyoom's first
    action — would leave the alert path down. Both together, exactly once,
    since systemd keeps the last assignment.
    """
    assert values(UNIT, "Restart") == ["always"]
    assert values(UNIT, "SuccessExitStatus") == ["143"]


BIND_OVERRIDE = "NOTIFIER_BIND_HOST"


def test_bind_override_is_not_baked_into_either_unit():
    """The override is for tests and diagnosis, never for a deployment.

    Same rule as NOTIFIER_ALLOW_PROD_DB one file over: a unit or env file that
    carried this would move the bind off the tailnet permanently and silently,
    undoing #43 D3 while every health check stayed green.
    """
    for unit in (UNIT, REPO_ROOT / "deploy" / "notifier-dev.service"):
        assert BIND_OVERRIDE not in directives(unit), f"{unit.name} pins the bind override"


@pytest.mark.parametrize(
    "env_file", [Path("/etc/notifier/.env"), REPO_ROOT / ".env"], ids=["etc", "repo"]
)
def test_bind_override_is_not_in_any_env_file_on_the_unit_load_path(env_file):
    """VM-local check. Skips loudly off-VM rather than passing vacuously."""
    if not env_file.exists():
        pytest.skip(f"{env_file} not present on this machine")
    assert BIND_OVERRIDE not in env_file.read_text()


TAILNET_WAIT = "NOTIFIER_TAILNET_WAIT_SECONDS"


def test_tailnet_wait_is_not_overridden_by_either_unit():
    """Both units' start-limit arithmetic reads tailnet_bind.sh's *default* wait (#143).

    A unit that set its own would move the slowest loop past the interval
    that counts it, and every arithmetic test would stay green.
    """
    for unit in (UNIT, REPO_ROOT / "deploy" / "notifier-dev.service"):
        assert TAILNET_WAIT not in directives(unit), f"{unit.name} overrides the tailnet wait"


@pytest.mark.parametrize(
    "env_file", [Path("/etc/notifier/.env"), REPO_ROOT / ".env"], ids=["etc", "repo"]
)
def test_tailnet_wait_is_not_in_any_env_file_on_the_unit_load_path(env_file):
    """VM-local check. Skips loudly off-VM rather than passing vacuously.

    Both units read these files — notifier.service through EnvironmentFile=,
    notifier-dev.service by sourcing them in dev_server.sh.
    """
    if not env_file.exists():
        pytest.skip(f"{env_file} not present on this machine")
    assert TAILNET_WAIT not in env_file.read_text()
