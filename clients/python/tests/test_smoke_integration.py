"""Integration smoke test against a live notifier on $NOTIFIER_URL (default :9001).

Requires:
- A notifier server reachable at $NOTIFIER_URL
- Either ($NOTIFIER_TENANT_ID + $NOTIFIER_API_KEY) provided, or the seed script
  is runnable from the repo root.

Per AGENTS.md, port 9000 belongs to systemd. Default for SDK dev tests is 9001.
"""

import pytest

from notifier_client import AUTO, NotifierClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_health_endpoint(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        result = await c.health()
    assert result.get("status") == "ok"


@pytest.mark.asyncio
async def test_inline_dispatch_with_auto_idempotency(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        # Skipped if the tenant has no channels — smoke covers the auth + render path.
        with pytest.raises(Exception) as exc:
            await c.dispatch(
                title_template="hello {{ who }}",
                body_template="body {{ who }}",
                variables={"who": "world"},
                channel_ids=["00000000000000000000000000"],   # bogus, will 404
                idempotency_key=AUTO,
            )
        # Expecting a 404 NotifierError — channel not found. The point is the
        # request reached the server and the auth worked.
        assert "404" in str(exc.value) or "not found" in str(exc.value).lower()
