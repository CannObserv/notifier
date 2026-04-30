import httpx
import pytest
import respx

from notifier_client.errors import RateLimited
from notifier_client.retry import RetryConfig, RetryTransport


@pytest.fixture
def fast_cfg():
    return RetryConfig(max_attempts=3, backoff_base=0.0)   # zero backoff for speed


async def _client(cfg: RetryConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://test.local",
        transport=RetryTransport(httpx.AsyncHTTPTransport(), cfg),
    )


@respx.mock
@pytest.mark.asyncio
async def test_retries_on_5xx_then_succeeds(fast_cfg):
    route = respx.get("https://test.local/health").mock(side_effect=[
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    ])
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_does_not_retry_on_4xx(fast_cfg):
    route = respx.get("https://test.local/health").mock(return_value=httpx.Response(404))
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 404
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_429_honors_retry_after_then_retries(fast_cfg):
    route = respx.get("https://test.local/health").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"ok": True}),
    ])
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_429_exhausted_returns_429_response(fast_cfg):
    # Transport doesn't raise — it returns the final response. The wrapper
    # converts that to RateLimited at the boundary.
    respx.get("https://test.local/health").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 429


@respx.mock
@pytest.mark.asyncio
async def test_per_request_no_retry_extension_disables_retries(fast_cfg):
    route = respx.post("https://test.local/dispatch").mock(return_value=httpx.Response(503))
    async with await _client(fast_cfg) as c:
        r = await c.post("/dispatch", json={}, extensions={"notifier_no_retry": True})
    assert r.status_code == 503
    assert route.call_count == 1
