"""Fan a rendered notification out to channels and log every attempt.

Extracted from ``src/api/routes/dispatch.py`` when monitors arrived (#56),
whose sweep had no HTTP request behind it. Monitors have since left for
co-status (#83), and the shape stays: this raises nothing HTTP-shaped and
commits nothing; rendering, validation, and ownership stay with the caller.

``redeliver`` retries a stored dispatch's failed channels as the next attempt
(#96), under the same rules: no HTTP, no commit.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.channel import Channel
from src.core.models.dispatch import Dispatch, DispatchAttempt
from src.core.notifications.constants import (
    MAX_ATTEMPTS_PER_CHANNEL,
    DispatchAttemptStatus,
    DispatchStatus,
)
from src.core.notifications.dispatcher import dispatch_to_channel


@dataclass(frozen=True)
class Delivery:
    """The Dispatch row and its per-channel attempts, both already added."""

    dispatch: Dispatch
    attempts: list[DispatchAttempt]


class RedeliveryExhausted(Exception):
    """Every failed channel has used all ``MAX_ATTEMPTS_PER_CHANNEL`` attempts."""

    def __init__(self, channel_ids: list[str]) -> None:
        super().__init__(f"attempt cap reached for channels {channel_ids}")
        self.channel_ids = channel_ids


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

    A channel listed twice is sent once: the attempt log holds one first
    attempt per channel, and a second would violate its unique constraint
    only *after* both sends went out.

    Adds and flushes rows but does not commit — the caller owns the
    transaction, so a route can still return a 4xx after this runs.
    """
    channels = list({c.id: c for c in channels}.values())
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

    attempts = [await _attempt(session, dispatch, channel, attempt=1) for channel in channels]
    successes = sum(a.status == DispatchAttemptStatus.SUCCEEDED for a in attempts)
    dispatch.status = aggregate_status(successes, len(channels))
    return Delivery(dispatch=dispatch, attempts=attempts)


async def redeliver(session: AsyncSession, dispatch: Dispatch) -> Delivery:
    """Retry each channel whose latest attempt failed, as its next attempt.

    Resends the stored render — nothing is re-rendered — through each
    channel's *current* URL, so fixing a channel and then redelivering works.
    Channels that succeeded are never sent again, and a channel already at
    ``MAX_ATTEMPTS_PER_CHANNEL`` is skipped; if that leaves failed channels
    but nothing to retry, raises ``RedeliveryExhausted``. A dispatch with no
    failed channel comes back untouched.

    The caller should hold the dispatch row ``FOR UPDATE``: two concurrent
    redeliveries would otherwise both claim the same attempt number. Returns
    every attempt, oldest first. Flushes but does not commit.
    """
    history = await attempts_of(session, dispatch.id)
    # By attempt number, not position: `history` is in clock order, and a
    # clock stepped back between attempts would otherwise pick a stale one.
    latest: dict[str, DispatchAttempt] = {}
    for attempt in history:
        seen = latest.get(str(attempt.channel_id))
        if seen is None or attempt.attempt > seen.attempt:
            latest[str(attempt.channel_id)] = attempt

    failed = [a for a in latest.values() if a.status == DispatchAttemptStatus.FAILED]
    if not failed:
        return Delivery(dispatch=dispatch, attempts=history)
    retryable = [a for a in failed if a.attempt < MAX_ATTEMPTS_PER_CHANNEL]
    if not retryable:
        raise RedeliveryExhausted([str(a.channel_id) for a in failed])

    result = await session.execute(
        select(Channel).where(
            Channel.id.in_([a.channel_id for a in retryable]),
            Channel.tenant_id == dispatch.tenant_id,
        )
    )
    channels = {str(c.id): c for c in result.scalars()}
    for prior in retryable:
        channel_id = str(prior.channel_id)
        retry = await _attempt(session, dispatch, channels[channel_id], attempt=prior.attempt + 1)
        history.append(retry)
        latest[channel_id] = retry

    successes = sum(a.status == DispatchAttemptStatus.SUCCEEDED for a in latest.values())
    dispatch.status = aggregate_status(successes, len(latest))
    await session.flush()
    return Delivery(dispatch=dispatch, attempts=history)


async def attempts_of(session: AsyncSession, dispatch_id: str) -> list[DispatchAttempt]:
    """Every attempt for a dispatch, oldest first — the order they were made."""
    result = await session.execute(
        select(DispatchAttempt)
        .where(DispatchAttempt.dispatch_id == dispatch_id)
        .order_by(DispatchAttempt.started_at)
    )
    return list(result.scalars().all())


async def _attempt(
    session: AsyncSession, dispatch: Dispatch, channel: Channel, *, attempt: int
) -> DispatchAttempt:
    """Send the dispatch's render to one channel and add the attempt row."""
    started = datetime.now(UTC)
    result = await dispatch_to_channel(
        apprise_url_encrypted=channel.apprise_url_encrypted,
        title=dispatch.rendered_title,
        body=dispatch.rendered_body,
    )
    row = DispatchAttempt(
        dispatch_id=dispatch.id,
        channel_id=channel.id,
        attempt=attempt,
        status=DispatchAttemptStatus.SUCCEEDED if result.success else DispatchAttemptStatus.FAILED,
        reason=result.reason,
        started_at=started,
        finished_at=datetime.now(UTC),
    )
    session.add(row)
    return row
