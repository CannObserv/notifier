"""Integration smoke test.

The conftest spawns a uvicorn subprocess wired to ``TEST_DATABASE_URL`` on an
ephemeral port, seeds a tenant against the same test DB, and tears both down
on session exit. Skips cleanly if ``TEST_DATABASE_URL`` is not set.
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
        with pytest.raises(Exception) as exc:
            await c.dispatch(
                title_template="hello {{ who }}",
                body_template="body {{ who }}",
                variables={"who": "world"},
                channel_ids=["00000000000000000000000000"],
                idempotency_key=AUTO,
            )
        assert "404" in str(exc.value) or "not found" in str(exc.value).lower()
