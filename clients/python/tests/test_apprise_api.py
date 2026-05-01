import json

import httpx
import pytest
import respx

from notifier_client import (
    AssembleResponse,
    NotifierClient,
    PluginDetail,
    PluginListItem,
    RetryConfig,
    ValidationError,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


_LIST_BODY = [
    {
        "plugin_schema": "slack",
        "service_name": "Slack",
        "category": "chat",
        "service_url": None,
        "setup_url": None,
    }
]
_DETAIL_BODY = {
    "plugin_schema": "slack",
    "service_name": "Slack",
    "tokens": {},
    "variants": [],
    "service_url": None,
    "setup_url": None,
}
_ASSEMBLE_BODY = {"apprise_url": "slack://hook/AAA/BBB"}


@respx.mock
@pytest.mark.asyncio
async def test_apprise_list_plugins_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/apprise/plugins").mock(
        return_value=httpx.Response(200, json=_LIST_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.apprise.list_plugins()
    assert len(result) == 1
    assert isinstance(result[0], PluginListItem)
    assert result[0].plugin_schema == "slack"
    assert result[0].service_name == "Slack"


@respx.mock
@pytest.mark.asyncio
async def test_apprise_get_plugin_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/apprise/plugins/slack").mock(
        return_value=httpx.Response(200, json=_DETAIL_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.apprise.get_plugin("slack")
    assert isinstance(result, PluginDetail)
    assert result.plugin_schema == "slack"


@respx.mock
@pytest.mark.asyncio
async def test_apprise_assemble_sends_tokens_and_returns_url(fast_retry):
    route = respx.post("https://t.local/api/v1/apprise/plugins/slack/assemble").mock(
        return_value=httpx.Response(200, json=_ASSEMBLE_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.apprise.assemble(
            "slack",
            tokens={"webhook_url": "https://hooks.slack.com/T000/B000/XXX"},
            variant_index=0,
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent["tokens"] == {"webhook_url": "https://hooks.slack.com/T000/B000/XXX"}
    assert sent["variant_index"] == 0
    assert isinstance(result, AssembleResponse)
    assert result.apprise_url == "slack://hook/AAA/BBB"


@respx.mock
@pytest.mark.asyncio
async def test_apprise_assemble_omits_variant_index_when_none(fast_retry):
    route = respx.post("https://t.local/api/v1/apprise/plugins/slack/assemble").mock(
        return_value=httpx.Response(200, json=_ASSEMBLE_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        await c.apprise.assemble("slack", tokens={"webhook_url": "https://hooks.slack.com/T000/B000/XXX"})
    sent = json.loads(route.calls.last.request.content)
    assert "variant_index" not in sent


@respx.mock
@pytest.mark.asyncio
async def test_apprise_assemble_validation_error(fast_retry):
    respx.post("https://t.local/api/v1/apprise/plugins/slack/assemble").mock(
        return_value=httpx.Response(422, json={"detail": [
            {"loc": ["body", "tokens", "webhook_url"], "msg": "field required", "type": "missing"}
        ]})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ValidationError) as exc:
            await c.apprise.assemble("slack", tokens={})
    assert exc.value.field_path == "body.tokens.webhook_url"
