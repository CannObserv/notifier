"""Core tests for ``src/core/notifications/delivery.py``.

The routes cover the paths a request can reach. These cover the stored
states a request cannot produce, inserted through the ORM.
"""

from datetime import UTC, datetime, timedelta

from src.core.crypto import encrypt_apprise_url
from src.core.models.channel import Channel
from src.core.models.dispatch import Dispatch, DispatchAttempt
from src.core.notifications.constants import DispatchAttemptStatus, DispatchStatus
from src.core.notifications.delivery import redeliver


class TestRedeliver:
    async def test_the_latest_attempt_is_the_highest_number_not_the_latest_clock(
        self, db_session, tenant, closed_port
    ):
        """CR 2: attempt 2 stamped *before* attempt 1 — a clock stepped back
        between them. Taking the last by `started_at` as latest retried as
        attempt 2 again and hit the unique constraint."""
        channel = Channel(
            tenant_id=tenant.id,
            name="skewed",
            apprise_url_encrypted=encrypt_apprise_url(f"json://127.0.0.1:{closed_port}/x"),
        )
        dispatch = Dispatch(
            tenant_id=tenant.id,
            rendered_title="t",
            rendered_body="b",
            status=DispatchStatus.FAILED,
        )
        db_session.add_all([channel, dispatch])
        await db_session.flush()
        now = datetime.now(UTC)
        for number, started in ((1, now), (2, now - timedelta(minutes=5))):
            db_session.add(
                DispatchAttempt(
                    dispatch_id=dispatch.id,
                    channel_id=channel.id,
                    attempt=number,
                    status=DispatchAttemptStatus.FAILED,
                    reason="Delivery failed",
                    started_at=started,
                    finished_at=started,
                )
            )
        await db_session.flush()

        delivery = await redeliver(db_session, dispatch)

        assert sorted(a.attempt for a in delivery.attempts) == [1, 2, 3]
        assert delivery.dispatch.status == DispatchStatus.FAILED
