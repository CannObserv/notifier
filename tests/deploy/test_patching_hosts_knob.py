"""The patching-hosts knob resolves clean for this host (#113).

``.skills/patching-hosts`` tells the vendored skill what only the owner knows:
the windows, the callers' quiet ranges, the data stores, the health checks.
A malformed line is never skipped: it makes the host report-only, so a run
the owner planned is refused at the gate rather than at commit time. The
vendored reader is the only honest parse, so this runs it.

Every database the cluster holds must be named, or the recovery point would
not cover it; the live check reads the cluster itself, with the probe's rule,
so a new database fails here rather than as a report-only host on the day of
a run. And the health checks must assert each port's own environment and
database, never ``build`` (#58).

The reader lives in the submodule, which CI checks out uninitialized, so
these skip there; the cluster check runs on this host alone.
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOB = REPO_ROOT / ".skills" / "patching-hosts"
#: Uninitialized in CI, which checks out without submodules.
READER = (
    REPO_ROOT
    / "skills-vendor"
    / "gregoryfoster-skills"
    / "skills"
    / "patching-hosts"
    / "scripts"
    / "read-knob.sh"
)
HOST = "notifier"
#: Each port, and the environment and database its /health names.
PORTS = {
    9000: ("production", "notifier"),
    9001: ("development", "notifier_dev"),
}
DATABASES = {"notifier", "notifier_dev", "notifier_test"}


def _resolve(config: Path) -> dict:
    if not READER.exists():
        pytest.skip("skills submodule not initialized")
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    out = subprocess.run(
        ["bash", str(READER), "--config", str(config), "--host", HOST],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


async def _cluster_databases(url: str) -> set[str]:
    """The databases the cluster holds, by the probe's rule: no templates, and
    ``postgres`` only while it holds a table of its own."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT datname FROM pg_database WHERE NOT datistemplate")
            )
            names = {r[0] for r in rows}
    finally:
        await engine.dispose()
    if "postgres" in names:
        engine = create_async_engine(make_url(url).set(database="postgres"))
        try:
            async with engine.connect() as conn:
                own = await conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN "
                        "('pg_catalog', 'information_schema')"
                    )
                )
        finally:
            await engine.dispose()
        if not own:
            names.discard("postgres")
    return names


@pytest.fixture(scope="module")
def knob() -> dict:
    return _resolve(KNOB)


def test_reader_flags_a_malformed_line(tmp_path: Path) -> None:
    """The control: without it, a reader that reports nothing passes below."""
    bad = tmp_path / "patching-hosts"
    bad.write_text(KNOB.read_text() + "window Tue 08:00-08:00\n")
    resolved = _resolve(bad)
    assert resolved["findings"]
    assert resolved["report_only"] is True


def test_knob_has_no_findings(knob: dict) -> None:
    assert knob["findings"] == []
    assert knob["report_only"] is False


def test_knob_is_a_scheduled_production_host(knob: dict) -> None:
    assert knob["class"]["value"] == "production"
    assert knob["posture"]["value"] == "scheduled"
    assert knob["window"]


def test_every_database_is_captured(knob: dict) -> None:
    named = {db for d in knob["datastore"] for db in d["databases"]}
    assert named == DATABASES


@pytest.mark.skipif(socket.gethostname() != HOST, reason=f"reads {HOST}'s live cluster")
def test_knob_names_every_database_the_cluster_holds(knob: dict) -> None:
    """The live cluster, not the constant above: CI's service database has
    other names, so this runs on this host alone."""
    named = {db for d in knob["datastore"] for db in d["databases"]}
    live = asyncio.run(_cluster_databases(os.environ["TEST_DATABASE_URL"]))
    assert live == named


def test_both_units_are_runbook_services(knob: dict) -> None:
    units = {s["unit"] for s in knob["service"]}
    assert units == {"notifier.service", "notifier-dev.service"}


@pytest.mark.parametrize("port", sorted(PORTS))
@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_each_endpoint_asserts_its_own_environment(knob: dict, port: int, path: str) -> None:
    environment, database = PORTS[port]
    lines = [h["command"] for h in knob["health"] if f":{port}{path}" in h["command"]]
    assert len(lines) == 1
    assert "tailscale ip -4" in lines[0]
    assert f'.environment == "{environment}"' in lines[0]
    assert f'.database == "{database}"' in lines[0]
    assert "build" not in lines[0]


def test_tailscale_is_followed_and_held(knob: dict) -> None:
    assert {(o["origin"], o["policy"]) for o in knob["origin"]} == {("Tailscale", "follow")}
    assert "tailscale" in {h["step"] for h in knob["hold"]}
