"""Fan a rendered notification out to channels and log every attempt.

Extracted from ``src/api/routes/dispatch.py`` when monitors arrived (#56):
three callers now need the same loop — the dispatch endpoint, a monitor
check-in carrying findings, and the sweep that fires on a *missing* check-in.
The sweep has no HTTP request behind it, so this deliberately raises nothing
HTTP-shaped and commits nothing; rendering, validation, and ownership stay
with the caller.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.channel import Channel
from src.core.models.dispatch import Dispatch, DispatchAttempt
from src.core.notifications.constants import DispatchAttemptStatus, DispatchStatus
from src.core.notifications.dispatcher import dispatch_to_channel


@dataclass(frozen=True)
class Delivery:
    """The Dispatch row and its per-channel attempts, both already added."""

    dispatch: Dispatch
    attempts: list[DispatchAttempt]


def aggregate_status(successes: int, total: int) -> str:
    """Roll per-channel outcomes into the Dispatch-level status.

    Zero channels is ``failed``: nothing was delivered, and reporting success
    for a notification that reached nobody is the failure mode this whole
    feature exists to prevent.
    """
    if total and successes == total:
        return DispatchStatus.SUCCEEDED
    if successes == 0:
        return DispatchStatus.FAILED
    return DispatchStatus.PARTIAL


async def deliver(
    session: AsyncSession,
    *,
    tenant_id: str,
    channels: list[Channel],
    rendered_title: str,
    rendered_body: str,
    variables: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    template_id: str | None = None,
    idempotency_key: str | None = None,
) -> Delivery:
    """Insert a Dispatch, deliver to each channel in order, record attempts.

    Adds and flushes rows but does not commit — the caller owns the
    transaction, so a route can still return a 4xx after this runs.
    """
    dispatch = Dispatch(
        tenant_id=tenant_id,
        template_id=template_id,
        idempotency_key=idempotency_key,
        rendered_title=rendered_title,
        rendered_body=rendered_body,
        variables=variables or {},
        request_metadata=metadata or {},
        status=DispatchStatus.FAILED,  # provisional; updated after attempts
    )
    session.add(dispatch)
    await session.flush()  # populate dispatch.id without releasing the txn

    successes = 0
    attempts: list[DispatchAttempt] = []
    for channel in channels:
        started = datetime.now(UTC)
        result = await dispatch_to_channel(
            apprise_url_encrypted=channel.apprise_url_encrypted,
            title=rendered_title,
            body=rendered_body,
        )
        finished = datetime.now(UTC)
        attempt = DispatchAttempt(
            dispatch_id=dispatch.id,
            channel_id=channel.id,
            attempt=1,
            status=(
                DispatchAttemptStatus.SUCCEEDED if result.success else DispatchAttemptStatus.FAILED
            ),
            reason=result.reason,
            started_at=started,
            finished_at=finished,
        )
        session.add(attempt)
        attempts.append(attempt)
        if result.success:
            successes += 1

    dispatch.status = aggregate_status(successes, len(channels))
    return Delivery(dispatch=dispatch, attempts=attempts)
