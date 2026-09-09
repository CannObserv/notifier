"""Tests for scripts/sweep_monitors.py — the timer's python entrypoint (#56).

Thin by design: the sweep itself is tested in tests/core/test_monitors.py.
What is only true here is that the pass gets *committed* and that the run
leaves a line in the journal. A sweep that alerts and then rolls back would
re-alert on every tick forever; a sweep that says nothing gives an operator no
way to tell "no monitors are overdue" from "the timer has not fired in a week".
"""

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from scripts.sweep_monitors import run_sweep
from src.core.crypto import encrypt_apprise_url
from src.core.models.channel import Channel
from src.core.models.monitor import Monitor
from src.core.monitors import MonitorState


@pytest.fixture
async def overdue_monitor(db_session, tenant, sink_server) -> Monitor:
    channel = Channel(
        tenant_id=tenant.id,
        name=f"c-{secrets.token_hex(4)}",
        apprise_url_encrypted=encrypt_apprise_url(f"json://127.0.0.1:{sink_server.port}/ok"),
    )
    db_session.add(channel)
    await db_session.flush()
    monitor = Monitor(
        tenant_id=tenant.id,
        name=f"m-{secrets.token_hex(4)}",
        interval_seconds=600,
        grace_seconds=1200,
        channel_ids=[str(channel.id)],
        title_template="t",
        body_template="b",
        state=MonitorState.OK,
        last_checkin_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(monitor)
    await db_session.flush()
    return monitor


async def test_the_pass_is_committed(db_session, overdue_monitor):
    """Not left in the session for a caller that never comes."""
    await run_sweep(db_session)

    await db_session.rollback()
    persisted = (
        await db_session.execute(select(Monitor).where(Monitor.id == overdue_monitor.id))
    ).scalar_one()
    assert persisted.state == MonitorState.MISSING


async def test_a_quiet_pass_still_reports_what_it_checked(db_session, overdue_monitor, caplog):
    """`checked=N alerted=0` is the line that proves the timer is alive."""
    with caplog.at_level("INFO"):
        report = await run_sweep(db_session)

    assert report.checked >= 1
    assert any("sweep" in record.message for record in caplog.records)
