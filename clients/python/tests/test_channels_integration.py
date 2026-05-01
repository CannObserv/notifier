"""Round-trip: channel create → list → dispatch → delete.

Exercises the typed sub-client surface against a real notifier process. The
channel uses a json:// Apprise URL — no external delivery, just confirms the
plumbing.

Note: ``DispatchAttempt.channel_id`` has ``ondelete="RESTRICT"`` at the DB
level, so a channel with recorded attempts cannot be deleted.  The test
therefore creates two channels: one used for dispatch (left in place after the
test) and one to verify delete (no dispatches through it).
"""

import uuid

import pytest

from notifier_client import NotifierClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_channel_round_trip(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    suffix = uuid.uuid4().hex[:8]
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        # 1. Create dispatch channel
        ch = await c.channels.create(
            name=f"round-trip-dispatch-{suffix}", apprise_url="json://localhost",
        )
        assert ch.id
        assert "round-trip-dispatch" in ch.name

        # 2. Create a separate channel to verify delete (no dispatches through it)
        ch_del = await c.channels.create(
            name=f"round-trip-delete-{suffix}", apprise_url="json://localhost",
        )
        assert ch_del.id

        try:
            # 3. List should include both
            listed = await c.channels.list()
            ids = {x.id for x in listed}
            assert ch.id in ids
            assert ch_del.id in ids

            # 4. Dispatch through dispatch channel
            result = await c.dispatch(
                title_template="t", body_template="b",
                channel_ids=[ch.id],
                idempotency_key=f"round-trip-{suffix}",
            )
            assert result.id
            assert result.status in {"succeeded", "failed", "partial"}

        finally:
            # 5. Delete the delete-only channel (no FK constraints on it)
            await c.channels.delete(ch_del.id)
            remaining = await c.channels.list()
            assert all(x.id != ch_del.id for x in remaining)
            # dispatch channel (ch) is left; FK prevents deletion without
            # cascade-clearing dispatch_attempts, which is out of scope here.
