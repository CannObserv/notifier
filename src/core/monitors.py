"""The dead-man's timer: deadlines, the alert decision, and the sweep (#56).

Alert on the *absence* of reports, not only on their contents. A findings-only
push is silent in exactly the cases that matter most — a dead probe, a stopped
timer, a wedged process, a dead node all produce zero findings and zero
traffic, which is indistinguishable from a healthy consumer.
CannObserv/observo#473 is what that costs: a crash-looped Redis left a cluster
starved for two weeks because nothing was watching for silence.

:func:`sweep_monitors` is the pass that watches. It is run by a systemd timer
(``deploy/notifier-sweep.timer``) rather than a task inside the API process,
for the same reason the issue gives against in-process probes: an alerter that
rides the thing it watches stops reporting exactly when it is needed. The
sweep talks to Postgres and Apprise and needs no part of the API to be up.
"""

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.core.models.channel import Channel
from src.core.models.dispatch import Dispatch
from src.core.models.monitor import Monitor
from src.core.notifications.delivery import deliver
from src.core.utils import format_utc_iso

logger = get_logger(__name__)


class MonitorState(enum.StrEnum):
    """Where a monitor stands relative to its deadline."""

    #: Created, but no check-in has ever arrived.
    PENDING = "pending"
    #: Reporting on time.
    OK = "ok"
    #: Past its deadline. Someone has been told.
    MISSING = "missing"


class CheckinStatus(enum.StrEnum):
    """What a consumer says about itself when it checks in.

    Deliberately two values. Whether a report *warrants* a notification is the
    consumer's judgement — a broker maps ``finding_count > 0`` onto ``alert``
    — because the alternative is notifier learning a consumer's taxonomy.
    """

    OK = "ok"
    ALERT = "alert"


def _as_utc(value: datetime) -> datetime:
    """Read a naive timestamp as UTC rather than raising mid-sweep.

    Postgres hands back aware datetimes for these columns, but a row built in
    a test or a fixture may not be. Comparing naive against aware raises
    TypeError, which inside the sweep would take out every monitor in the
    batch rather than the one bad row.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def deadline_for(monitor: Monitor) -> datetime:
    """When this monitor's next check-in stops being late and starts being an
    outage.

    Anchored on ``created_at`` before the first check-in ever arrives — a
    probe that was never wired up is the most likely misconfiguration of all,
    and anchoring on ``last_checkin_at`` alone would make it the one case the
    timer stays silent about forever.
    """
    anchor = monitor.last_checkin_at or monitor.created_at
    return _as_utc(anchor) + timedelta(
        seconds=monitor.interval_seconds + (monitor.grace_seconds or 0)
    )


def is_overdue(monitor: Monitor, now: datetime) -> bool:
    """True once ``now`` is past the deadline. The deadline itself is not late."""
    return now > deadline_for(monitor)


def should_alert(monitor: Monitor, now: datetime) -> bool:
    """Whether this pass should notify about this monitor.

    Fires on the crossing into ``missing``. Without the state check the sweep
    would page every 60 seconds until someone acted; ``renotify_seconds`` is
    the opt-in for the opposite failure, where the single alert is the one
    nobody saw.
    """
    if not monitor.enabled or not is_overdue(monitor, now):
        return False
    if monitor.state != MonitorState.MISSING:
        return True
    if monitor.renotify_seconds is None:
        return False
    if monitor.last_alert_at is None:
        return True
    return now - _as_utc(monitor.last_alert_at) >= timedelta(seconds=monitor.renotify_seconds)


def format_duration(delta: timedelta) -> str:
    """Render a duration in human units — ``1h 30m 30s``, ``10m``, ``1d 1h``.

    Alert bodies quote elapsed time, and an operator woken at 3am should not
    be dividing seconds by 3600. Trailing zero units are dropped; a negative
    duration (a clock that moved backwards) reads as ``0s`` rather than
    printing something impossible.
    """
    total = int(max(delta.total_seconds(), 0))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = [
        f"{value}{unit}"
        for value, unit in ((days, "d"), (hours, "h"), (minutes, "m"), (seconds, "s"))
        if value
    ]
    return " ".join(parts) if parts else "0s"


def _cadence(monitor: Monitor) -> str:
    expected = format_duration(timedelta(seconds=monitor.interval_seconds))
    grace = format_duration(timedelta(seconds=monitor.grace_seconds or 0))
    return f"every {expected} (grace {grace})"


def _last_seen(monitor: Monitor) -> str:
    if monitor.last_checkin_at is None:
        return "never — no check-in has ever arrived"
    return format_utc_iso(_as_utc(monitor.last_checkin_at))


def missing_notification(monitor: Monitor, now: datetime) -> tuple[str, str]:
    """Title and body for a monitor that has gone quiet.

    Built in rather than configurable: a consumer that has stopped reporting
    cannot supply a template for the fact that it stopped reporting.
    """
    silence = format_duration(now - _as_utc(monitor.last_checkin_at or monitor.created_at))
    title = f"[notifier] {monitor.name} has stopped reporting"
    body = (
        f"No check-in from **{monitor.name}** for {silence}.\n\n"
        f"- Expected: {_cadence(monitor)}\n"
        f"- Last check-in: {_last_seen(monitor)}\n"
        f"- Deadline passed: {format_utc_iso(deadline_for(monitor))}\n\n"
        "Silence is the alert: the reporter itself may be down, wedged, or "
        "never started."
    )
    return title, body


def recovery_notification(monitor: Monitor, now: datetime) -> tuple[str, str]:
    """Title and body for a monitor that is reporting again.

    Without this the outage alert stays the last word on a problem that is
    over, and the next real one is read as noise.
    """
    silence = format_duration(now - _as_utc(monitor.last_checkin_at or monitor.created_at))
    title = f"[notifier] {monitor.name} has recovered"
    body = (
        f"**{monitor.name}** is reporting again after {silence} of silence.\n\n"
        f"- Expected: {_cadence(monitor)}\n"
        f"- Previous check-in: {_last_seen(monitor)}"
    )
    return title, body


@dataclass
class SweepReport:
    """What one pass did — the payload of the timer's journald line."""

    checked: int = 0
    alerted: list[str] = field(default_factory=list)
    #: Overdue monitors that had nowhere to send: no channels, or every
    #: configured channel id has since been deleted.
    undeliverable: list[str] = field(default_factory=list)
    dispatches: list[Dispatch] = field(default_factory=list)


async def resolve_channels(session: AsyncSession, monitor: Monitor) -> list[Channel]:
    """Resolve a monitor's channel ids, dropping any that no longer exist.

    ``channel_ids`` is an array, not a foreign key, so ids can go stale. One
    monitor pointing at a vanished channel must not stop the sweep alerting on
    every other monitor in the pass.
    """
    if not monitor.channel_ids:
        return []
    result = await session.execute(
        select(Channel).where(
            Channel.id.in_(monitor.channel_ids), Channel.tenant_id == monitor.tenant_id
        )
    )
    by_id = {str(c.id): c for c in result.scalars().all()}
    return [by_id[cid] for cid in monitor.channel_ids if cid in by_id]


async def sweep_monitors(session: AsyncSession, now: datetime | None = None) -> SweepReport:
    """Alert on every enabled monitor that has missed its deadline.

    Does not commit — the caller owns the transaction, so ``scripts/
    sweep_monitors.py`` commits once for the whole pass.

    A monitor is marked ``missing`` whether or not the notification reached
    anyone. State describes the consumer, not our luck reaching Slack: leaving
    it ``ok`` on a bounced alert would re-alert on every pass forever *and*
    would keep reporting a dead consumer as healthy.
    """
    now = now or datetime.now(UTC)
    report = SweepReport()

    result = await session.execute(select(Monitor).where(Monitor.enabled.is_(True)))
    for monitor in result.scalars().all():
        report.checked += 1
        if not should_alert(monitor, now):
            continue

        title, body = missing_notification(monitor, now)
        channels = await resolve_channels(session, monitor)
        if channels:
            delivery = await deliver(
                session,
                tenant_id=monitor.tenant_id,
                channels=channels,
                rendered_title=title,
                rendered_body=body,
                metadata={"monitor_id": str(monitor.id), "reason": "missing"},
            )
            report.dispatches.append(delivery.dispatch)
            report.alerted.append(str(monitor.id))
        else:
            report.undeliverable.append(str(monitor.id))
            logger.warning(
                "monitor is overdue but has no deliverable channel",
                extra={"monitor_id": str(monitor.id), "monitor_name": monitor.name},
            )

        monitor.state = MonitorState.MISSING
        monitor.last_alert_at = now

    return report
