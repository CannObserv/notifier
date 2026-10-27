"""Drift tests for deploy/notifier-dev.service — the persistent dev endpoint.

The dev unit is the mirror image of the production one. `notifier.service`
must carry the production opt-in; this unit must never carry it. Watcher's
non-production processes point here (watcher#278 step 2), and the whole value
of a `development`-marked key is that it cannot reach production — a unit that
inherited the opt-in would quietly undo that.

It also must not spell out its own uvicorn line. `scripts/dev_server.sh`
already unsets the opt-in, swaps in DEV_DATABASE_URL, delegates the URL check
to src.core.db_safety, and refuses an unmigrated database (#23). A second
ExecStart spelling is a second code path that can drift out from under all
four checks.
"""

import re

from src.core import db_safety
from tests.deploy.systemd_units import (
    REPO_ROOT,
    directives,
    seconds,
    tailnet_wait_seconds,
    values,
)

DEV_UNIT = REPO_ROOT / "deploy" / "notifier-dev.service"
PROD_UNIT = REPO_ROOT / "deploy" / "notifier.service"


def test_dev_unit_exists():
    assert DEV_UNIT.is_file()


def test_dev_unit_never_carries_the_production_opt_in():
    """The mirror of test_unit_sets_the_production_opt_in_flag."""
    assert db_safety.ALLOW_PROD_ENV_VAR not in directives(DEV_UNIT), (
        "the production opt-in belongs to notifier.service alone; on this "
        "unit it would let the dev endpoint open the production database"
    )


def test_dev_unit_launches_through_the_guarded_script():
    """Not a hand-rolled uvicorn line — that bypasses every guard in #22/#23."""
    body = directives(DEV_UNIT)
    assert "scripts/dev_server.sh" in body
    assert "uvicorn" not in body


def test_dev_unit_does_not_pin_a_database_url():
    """DATABASE_URL is derived from DEV_DATABASE_URL by the script, once."""
    assert "Environment=DATABASE_URL" not in directives(DEV_UNIT)


def test_dev_unit_disables_the_reloader():
    """A wedged reloader keeps running, so no Restart= policy ever fires."""
    assert "Environment=NOTIFIER_DEV_RELOAD=0" in directives(DEV_UNIT)


def test_dev_unit_stays_off_the_production_port():
    assert "9000" not in directives(DEV_UNIT)


def test_dev_unit_bounds_its_restart_loop():
    """An unmigrated dev DB exits non-zero by design; don't loop on it forever."""
    assert seconds(DEV_UNIT, "StartLimitBurst") == 5
    assert seconds(DEV_UNIT, "StartLimitIntervalSec") == 600
    assert seconds(DEV_UNIT, "RestartSec") == 15


def test_dev_unit_restarts_on_any_exit_systemd_did_not_ask_for():
    """#143, the same pair as the production unit.

    The dev endpoint is where the SIGTERM probe runs: an earlyoom-style kill
    of the uvicorn child must bring it back, and a ``systemctl restart`` must
    not log ``Failed``.
    """
    assert values(DEV_UNIT, "Restart") == ["always"]
    assert values(DEV_UNIT, "SuccessExitStatus") == ["143"]


def test_dev_unit_survives_a_slow_database_at_boot():
    """The bound must outlast a boot race, not just an unmigrated database.

    A unit that trips StartLimitBurst stays failed until someone runs
    `systemctl reset-failed`, leaving the endpoint silently down — the exact
    outcome #24 exists to prevent.
    `After=postgresql.service` orders startup but does not wait for the
    cluster to accept connections.

    One minute of retries distinguishes a slow boot from a real
    misconfiguration, which no amount of waiting will fix.

    The ceiling is the slowest loop, not the fastest: since #43 a start can
    wait the full tailnet bound before failing, and under ``Restart=always``
    (#143) every start counts. If that loop fits inside the interval, the
    limit can always trip.
    """
    burst = seconds(DEV_UNIT, "StartLimitBurst")
    fastest = burst * seconds(DEV_UNIT, "RestartSec")
    slowest = burst * (tailnet_wait_seconds() + seconds(DEV_UNIT, "RestartSec"))
    assert fastest >= 60, f"gives up after {fastest}s — too fast to ride out a slow Postgres"
    assert slowest <= seconds(DEV_UNIT, "StartLimitIntervalSec"), (
        f"{burst} slow failures take {slowest}s, longer than the window that counts "
        "them — the limit never trips and the loop runs forever"
    )


def test_dev_unit_reports_which_commit_it_is_serving():
    """/health on :9001 must not answer `dev` while :9000 answers a SHA (#24).

    A bug reported against the dev endpoint is unactionable without it. Kept
    off the production unit's /run/notifier/build-id so the two units never
    race to write one file.
    """
    body = directives(DEV_UNIT)
    assert "BUILD_ID=" in body
    assert "build-id-dev" in body
    # Every mention must be the -dev file. An end-of-line check would miss the
    # one that matters: the write target sits mid-line inside the ExecStartPre
    # shell quoting, and reverting only that half is what recreates the race.
    assert re.search(r"/run/notifier/build-id(?!-dev)", body) is None


def test_dev_unit_starts_at_boot():
    """Persistent means persistent — it must survive a VM reboot (#24)."""
    assert "WantedBy=multi-user.target" in directives(DEV_UNIT)


def test_the_two_units_do_not_collide_on_a_port():
    """Both ExecStarts are scripts now (#43), so the ports live there."""
    assert "--port 9000" in (REPO_ROOT / "scripts" / "serve.sh").read_text()
    assert "9001" not in directives(PROD_UNIT)
    assert "9001" in (REPO_ROOT / "scripts" / "dev_server.sh").read_text()


def test_dev_unit_orders_after_tailscaled():
    """Same boot race as the production unit (#43 R1 / observo#473)."""
    after = [line for line in directives(DEV_UNIT).splitlines() if line.startswith("After=")]
    assert after and any("tailscaled.service" in line for line in after)
