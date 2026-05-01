import httpx
import pytest
import respx

from notifier_client import (
    ChannelOut,
    ChannelTestResponse,
    NotifierClient,
    RetryConfig,
    ValidationError,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


_CHANNEL_BODY = {
    "id": "01HA", "tenant_id": "t1", "name": "ops",
    "apprise_url_masked": "slack://***", "channel_hint": "slack",
    "created_at": "2026-04-30T00:00:00Z",
    "updated_at": "2026-04-30T00:00:00Z",
}


@respx.mock
@pytest.mark.asyncio
async def test_channels_list_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(200, json=[_CHANNEL_BODY])
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.list()
    assert len(result) == 1
    assert isinstance(result[0], ChannelOut)
    assert result[0].name == "ops"


@respx.mock
@pytest.mark.asyncio
async def test_channels_create_sends_body_and_returns_typed(fast_retry):
    route = respx.post("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(201, json=_CHANNEL_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.create(
            name="ops", apprise_url="slack://hook/AAA/BBB", channel_hint="slack",
        )
    body = route.calls.last.request.read().decode()
    assert "slack://hook/AAA/BBB" in body
    assert isinstance(result, ChannelOut)


@respx.mock
@pytest.mark.asyncio
async def test_channels_get_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(200, json=_CHANNEL_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.get("01HA")
    assert isinstance(result, ChannelOut)
    assert result.id == "01HA"


@respx.mock
@pytest.mark.asyncio
async def test_channels_update_patches_and_returns_typed(fast_retry):
    route = respx.patch("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(200, json={**_CHANNEL_BODY, "name": "renamed"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.update("01HA", name="renamed")
    body = route.calls.last.request.read().decode()
    assert "renamed" in body
    assert "apprise_url" not in body  # only supplied fields are sent
    assert result.name == "renamed"


@respx.mock
@pytest.mark.asyncio
async def test_channels_delete_returns_none(fast_retry):
    respx.delete("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(204)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.delete("01HA")
    assert result is None


@respx.mock
@pytest.mark.asyncio
async def test_channels_test_returns_typed(fast_retry):
    respx.post("https://t.local/api/v1/channels/01HA/test").mock(
        return_value=httpx.Response(200, json={"success": True, "reason": "ok"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.test("01HA")
    assert isinstance(result, ChannelTestResponse)
    assert result.success is True


@respx.mock
@pytest.mark.asyncio
async def test_channels_create_validation_error(fast_retry):
    respx.post("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(422, json={"detail": [
            {"loc": ["body", "apprise_url"], "msg": "field required", "type": "missing"}
        ]})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ValidationError) as exc:
            await c.channels.create(name="ops", apprise_url="")
    assert exc.value.field_path == "body.apprise_url"
