"""Dead-man's-timer logic and the sweep that fires it (#56).

A findings-only push is silent in exactly the cases that matter — a stopped
timer, a wedged process, a dead node all produce zero findings and zero
traffic, indistinguishable from health. CannObserv/observo#473 is what that
costs. So the alerting condition tested here is *absence*: a monitor whose
deadline has passed is itself the alert.

Nothing here is mocked. Delivery goes to a local sink returning 200 or to a
port where the connection is refused, so an alert that claims to have been
delivered really was.
"""

import secrets
from datetime import UTC, datetime, timedelta

import pytest

from src.core.crypto import encrypt_apprise_url
from src.core.models.channel import Channel
from src.core.models.monitor import Monitor
from src.core.monitors import (
    CheckinStatus,
    MonitorState,
    deadline_for,
    format_duration,
    is_overdue,
    missing_notification,
    recovery_notification,
    should_alert,
    sweep_monitors,
)
from src.core.notifications.constants import DispatchStatus

NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)


def _monitor(**overrides) -> Monitor:
    """An unsaved Monitor with the broker's cadence: ten minutes, 20m grace."""
    fields = {
        "tenant_id": "01J0000000000000000000000A",
        "name": "co-broker",
        "enabled": True,
        "interval_seconds": 600,
        "grace_seconds": 1200,
        "renotify_seconds": None,
        "channel_ids": [],
        "title_template": "t",
        "body_template": "b",
        "state": MonitorState.PENDING,
        "created_at": NOW - timedelta(minutes=5),
        "last_checkin_at": None,
        "last_alert_at": None,
    }
    fields.update(overrides)
    return Monitor(**fields)


class TestDeadline:
    """When the next report is due, and what the clock starts from."""

    def test_runs_from_the_last_checkin(self):
        monitor = _monitor(last_checkin_at=NOW - timedelta(minutes=1))
        assert deadline_for(monitor) == NOW - timedelta(minutes=1) + timedelta(seconds=1800)

    def test_falls_back_to_creation_when_nothing_has_ever_checked_in(self):
        """A monitor that never reports at all must still alert.

        Anchoring on ``last_checkin_at`` alone would make a probe that was
        never wired up — the most likely misconfiguration of all — the one
        case the timer stays silent about, forever.
        """
        monitor = _monitor(created_at=NOW - timedelta(hours=2), last_checkin_at=None)
        assert deadline_for(monitor) == NOW - timedelta(hours=2) + timedelta(seconds=1800)

    def test_grace_extends_the_deadline_past_a_single_missed_tick(self):
        """Ten-minute cadence, 20 minutes of grace: two ticks may be lost."""
        monitor = _monitor(last_checkin_at=NOW, interval_seconds=600, grace_seconds=1200)
        assert deadline_for(monitor) == NOW + timedelta(minutes=30)

    def test_naive_timestamps_are_read_as_utc(self):
        """Postgres hands back aware datetimes; a hand-built row may not.

        Comparing a naive stored value against an aware ``now`` raises
        TypeError inside the sweep, which would take out every monitor in the
        batch rather than the one bad row.
        """
        monitor = _monitor(last_checkin_at=datetime(2026, 9, 9, 11, 0, 0))
        assert deadline_for(monitor) == datetime(2026, 9, 9, 11, 30, tzinfo=UTC)


class TestIsOverdue:
    def test_not_overdue_before_the_deadline(self):
        assert is_overdue(_monitor(last_checkin_at=NOW - timedelta(minutes=29)), NOW) is False

    def test_overdue_after_the_deadline(self):
        assert is_overdue(_monitor(last_checkin_at=NOW - timedelta(minutes=31)), NOW) is True

    def test_the_deadline_itself_is_not_yet_late(self):
        assert is_overdue(_monitor(last_checkin_at=NOW - timedelta(minutes=30)), NOW) is False


class TestShouldAlert:
    """Which overdue monitors get a notification on this pass."""

    def test_alerts_on_the_first_crossing(self):
        monitor = _monitor(last_checkin_at=NOW - timedelta(hours=1), state=MonitorState.OK)
        assert should_alert(monitor, NOW) is True

    def test_a_disabled_monitor_never_alerts(self):
        """Paused for planned downtime, not deleted."""
        monitor = _monitor(
            enabled=False, last_checkin_at=NOW - timedelta(hours=1), state=MonitorState.OK
        )
        assert should_alert(monitor, NOW) is False

    def test_does_not_re_alert_while_already_missing(self):
        """Without this the sweep pages every 60 seconds until someone acts."""
        monitor = _monitor(
            last_checkin_at=NOW - timedelta(hours=1),
            state=MonitorState.MISSING,
            last_alert_at=NOW - timedelta(minutes=5),
        )
        assert should_alert(monitor, NOW) is False

    def test_renotifies_once_the_configured_interval_has_elapsed(self):
        monitor = _monitor(
            last_checkin_at=NOW - timedelta(hours=6),
            state=MonitorState.MISSING,
            last_alert_at=NOW - timedelta(hours=4),
            renotify_seconds=3600,
        )
        assert should_alert(monitor, NOW) is True

    def test_holds_the_renotify_interval(self):
        monitor = _monitor(
            last_checkin_at=NOW - timedelta(hours=6),
            state=MonitorState.MISSING,
            last_alert_at=NOW - timedelta(minutes=10),
            renotify_seconds=3600,
        )
        assert should_alert(monitor, NOW) is False

    def test_renotify_with_no_prior_alert_fires(self):
        """A row that reached ``missing`` before an alert could be delivered."""
        monitor = _monitor(
            last_checkin_at=NOW - timedelta(hours=6),
            state=MonitorState.MISSING,
            last_alert_at=None,
            renotify_seconds=3600,
        )
        assert should_alert(monitor, NOW) is True


class TestFormatDuration:
    """Alert bodies quote elapsed time; seconds-since-epoch helps nobody."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0s"),
            (45, "45s"),
            (60, "1m"),
            (615, "10m 15s"),
            (3600, "1h"),
            (5430, "1h 30m 30s"),
            (90000, "1d 1h"),
        ],
    )
    def test_renders_human_units(self, seconds, expected):
        assert format_duration(timedelta(seconds=seconds)) == expected

    def test_negative_durations_read_as_zero(self):
        assert format_duration(timedelta(seconds=-5)) == "0s"


class TestBuiltInNotifications:
    """Missing and recovery wording is notifier's, not the consumer's.

    A consumer that has stopped reporting cannot supply a template for the
    fact that it stopped reporting, so these are built in.
    """

    def test_missing_names_the_monitor_and_the_silence(self):
        monitor = _monitor(name="co-broker", last_checkin_at=NOW - timedelta(minutes=47))
        title, body = missing_notification(monitor, NOW)
        assert "co-broker" in title
        assert "47m" in body
        assert "10m" in body  # the expected cadence

    def test_missing_says_never_when_nothing_ever_arrived(self):
        monitor = _monitor(last_checkin_at=None, created_at=NOW - timedelta(hours=3))
        _, body = missing_notification(monitor, NOW)
        assert "never" in body.lower()

    def test_recovery_names_the_silence_that_ended(self):
        monitor = _monitor(name="co-broker", last_checkin_at=NOW - timedelta(hours=2))
        title, body = recovery_notification(monitor, NOW)
        assert "co-broker" in title
        assert "2h" in body


@pytest.fixture
async def channel(db_session, tenant, closed_port) -> Channel:
    """A channel whose Apprise URL is unreachable — delivery fails, honestly."""
    c = Channel(
        tenant_id=tenant.id,
        name=f"c-{secrets.token_hex(4)}",
        apprise_url_encrypted=encrypt_apprise_url(f"json://127.0.0.1:{closed_port}/nope"),
    )
    db_session.add(c)
    await db_session.flush()
    return c


@pytest.fixture
async def good_channel(db_session, tenant, sink_server) -> Channel:
    c = Channel(
        tenant_id=tenant.id,
        name=f"c-{secrets.token_hex(4)}",
        apprise_url_encrypted=encrypt_apprise_url(f"json://127.0.0.1:{sink_server.port}/ok"),
    )
    db_session.add(c)
    await db_session.flush()
    return c


async def _save(db_session, tenant, channels, **overrides) -> Monitor:
    fields = {
        "tenant_id": tenant.id,
        "name": f"m-{secrets.token_hex(4)}",
        "channel_ids": [str(c.id) for c in channels],
    }
    fields.update(overrides)
    monitor = _monitor(**fields)
    db_session.add(monitor)
    await db_session.flush()
    return monitor


class TestSweepMonitors:
    """The pass a systemd timer runs; the only thing watching for silence."""

    async def test_overdue_monitor_is_alerted_and_marked_missing(
        self, db_session, tenant, good_channel
    ):
        monitor = await _save(
            db_session, tenant, [good_channel], last_checkin_at=NOW - timedelta(hours=1)
        )
        report = await sweep_monitors(db_session, now=NOW)

        assert report.alerted == [str(monitor.id)]
        assert monitor.state == MonitorState.MISSING
        assert monitor.last_alert_at == NOW

    async def test_alert_is_really_delivered_and_logged_as_a_dispatch(
        self, db_session, tenant, good_channel
    ):
        monitor = await _save(
            db_session, tenant, [good_channel], last_checkin_at=NOW - timedelta(hours=1)
        )
        report = await sweep_monitors(db_session, now=NOW)

        (dispatch,) = report.dispatches
        assert dispatch.tenant_id == tenant.id
        assert dispatch.status == DispatchStatus.SUCCEEDED
        assert monitor.name in dispatch.rendered_title

    async def test_a_failed_delivery_still_marks_the_monitor_missing(
        self, db_session, tenant, channel
    ):
        """State is about the consumer, not about our luck reaching Slack.

        Leaving it ``ok`` because the notification bounced would re-alert on
        every pass forever, and would misreport the consumer as healthy.
        """
        monitor = await _save(
            db_session, tenant, [channel], last_checkin_at=NOW - timedelta(hours=1)
        )
        report = await sweep_monitors(db_session, now=NOW)

        assert monitor.state == MonitorState.MISSING
        assert report.dispatches[0].status == DispatchStatus.FAILED

    async def test_a_healthy_monitor_is_left_alone(self, db_session, tenant, good_channel):
        monitor = await _save(
            db_session,
            tenant,
            [good_channel],
            state=MonitorState.OK,
            last_checkin_at=NOW - timedelta(minutes=2),
        )
        report = await sweep_monitors(db_session, now=NOW)

        assert report.alerted == []
        assert monitor.state == MonitorState.OK

    async def test_a_disabled_monitor_is_skipped_entirely(self, db_session, tenant, good_channel):
        monitor = await _save(
            db_session,
            tenant,
            [good_channel],
            enabled=False,
            last_checkin_at=NOW - timedelta(days=3),
        )
        report = await sweep_monitors(db_session, now=NOW)

        assert report.alerted == []
        assert monitor.state == MonitorState.PENDING

    async def test_an_already_missing_monitor_is_not_re_alerted(
        self, db_session, tenant, good_channel
    ):
        await _save(
            db_session,
            tenant,
            [good_channel],
            state=MonitorState.MISSING,
            last_checkin_at=NOW - timedelta(hours=5),
            last_alert_at=NOW - timedelta(hours=4),
        )
        report = await sweep_monitors(db_session, now=NOW)
        assert report.alerted == []

    async def test_a_monitor_with_no_channels_is_marked_but_not_dispatched(
        self, db_session, tenant
    ):
        """Nowhere to send is a configuration fault, not a reason to retry.

        The sweep records the state change so the row stops looking healthy,
        and reports the monitor as skipped so the timer's journald line names
        it.
        """
        monitor = await _save(db_session, tenant, [], last_checkin_at=NOW - timedelta(hours=1))
        report = await sweep_monitors(db_session, now=NOW)

        assert report.dispatches == []
        assert str(monitor.id) in report.undeliverable
        assert monitor.state == MonitorState.MISSING

    async def test_a_deleted_channel_does_not_take_out_the_whole_sweep(
        self, db_session, tenant, good_channel
    ):
        """``channel_ids`` is a list, not a foreign key: ids can go stale.

        One monitor pointing at a vanished channel must not stop the sweep
        from alerting on every other monitor in the pass.
        """
        stale = await _save(
            db_session,
            tenant,
            [],
            channel_ids=["01J0000000000000000000000B"],
            last_checkin_at=NOW - timedelta(hours=1),
        )
        live = await _save(
            db_session, tenant, [good_channel], last_checkin_at=NOW - timedelta(hours=1)
        )
        report = await sweep_monitors(db_session, now=NOW)

        assert str(live.id) in report.alerted
        assert str(stale.id) in report.undeliverable

    async def test_defaults_to_the_wall_clock(self, db_session, tenant, good_channel):
        """``now`` is injectable for tests; production passes nothing."""
        await _save(
            db_session,
            tenant,
            [good_channel],
            last_checkin_at=datetime.now(UTC) - timedelta(days=1),
        )
        report = await sweep_monitors(db_session)
        assert len(report.alerted) == 1


class TestCheckinStatus:
    def test_values_are_the_wire_strings(self):
        assert CheckinStatus.OK == "ok"
        assert CheckinStatus.ALERT == "alert"

    def test_monitor_states_are_the_wire_strings(self):
        assert MonitorState.PENDING == "pending"
        assert MonitorState.OK == "ok"
        assert MonitorState.MISSING == "missing"
