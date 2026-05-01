import httpx
import pytest
import respx

from notifier_client import NotifierClient, PreviewResponse, RetryConfig


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


@respx.mock
@pytest.mark.asyncio
async def test_preview_renders_inline(fast_retry):
    route = respx.post("https://t.local/api/v1/preview").mock(
        return_value=httpx.Response(200, json={
            "title": "hello world", "body": "body world",
            "error": None, "error_section": None,
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.preview(
            title_template="hello {{ who }}",
            body_template="body {{ who }}",
            variables={"who": "world"},
        )
    body = route.calls.last.request.read().decode()
    assert "hello {{ who }}" in body
    assert "body {{ who }}" in body
    assert "world" in body
    assert isinstance(result, PreviewResponse)
    assert result.title == "hello world"


@respx.mock
@pytest.mark.asyncio
async def test_preview_returns_error_section(fast_retry):
    respx.post("https://t.local/api/v1/preview").mock(
        return_value=httpx.Response(200, json={
            "title": None, "body": None,
            "error": "undefined variable", "error_section": "title",
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.preview(
            title_template="{{ missing }}", body_template="b", variables={},
        )
    assert result.error_section == "title"
    assert result.error == "undefined variable"
