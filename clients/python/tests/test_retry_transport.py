import httpx2
import pytest
import respx

from notifier_client.retry import RetryConfig, RetryTransport


@pytest.fixture
def fast_cfg():
    return RetryConfig(max_attempts=3, backoff_base=0.0)  # zero backoff for speed


async def _client(cfg: RetryConfig) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url="https://test.local",
        transport=RetryTransport(httpx2.AsyncHTTPTransport(), cfg),
    )


@respx.mock
@pytest.mark.asyncio
async def test_retries_on_5xx_then_succeeds(fast_cfg):
    route = respx.get("https://test.local/health").mock(
        side_effect=[
            httpx2.Response(503),
            httpx2.Response(503),
            httpx2.Response(200, json={"ok": True}),
        ]
    )
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_does_not_retry_on_4xx(fast_cfg):
    route = respx.get("https://test.local/health").mock(return_value=httpx2.Response(404))
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 404
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_429_honors_retry_after_then_retries(fast_cfg):
    route = respx.get("https://test.local/health").mock(
        side_effect=[
            httpx2.Response(429, headers={"Retry-After": "0"}),
            httpx2.Response(200, json={"ok": True}),
        ]
    )
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
        return_value=httpx2.Response(429, headers={"Retry-After": "0"})
    )
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 429


@respx.mock
@pytest.mark.asyncio
async def test_per_request_no_retry_extension_disables_retries(fast_cfg):
    route = respx.post("https://test.local/dispatch").mock(return_value=httpx2.Response(503))
    async with await _client(fast_cfg) as c:
        r = await c.post("/dispatch", json={}, extensions={"notifier_no_retry": True})
    assert r.status_code == 503
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_retries_on_network_error_then_succeeds(fast_cfg):
    route = respx.get("https://test.local/health").mock(
        side_effect=[
            httpx2.ConnectError("connection refused"),
            httpx2.ReadTimeout("read timeout"),
            httpx2.Response(200, json={"ok": True}),
        ]
    )
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_network_error_exhaustion_reraises(fast_cfg):
    respx.get("https://test.local/health").mock(side_effect=httpx2.ConnectError("nope"))
    async with await _client(fast_cfg) as c:
        with pytest.raises(httpx2.ConnectError):
            await c.get("/health")


@respx.mock
@pytest.mark.asyncio
async def test_network_error_retry_disabled():
    cfg = RetryConfig(max_attempts=3, backoff_base=0.0, retry_on_network_error=False)
    route = respx.get("https://test.local/health").mock(side_effect=httpx2.ConnectError("nope"))
    async with await _client(cfg) as c:
        with pytest.raises(httpx2.ConnectError):
            await c.get("/health")
    assert route.call_count == 1


def test_max_attempts_zero_rejected():
    with pytest.raises(ValueError, match="max_attempts must be >= 1"):
        RetryConfig(max_attempts=0)


@respx.mock
@pytest.mark.asyncio
async def test_network_error_and_5xx_share_retry_budget():
    # max_attempts=4: ConnectError (attempt 1) → 503 (attempt 2) → 200 (attempt 3).
    # Both retry pathways draw from the same `attempt` counter.
    cfg = RetryConfig(max_attempts=4, backoff_base=0.0)
    route = respx.get("https://test.local/health").mock(
        side_effect=[
            httpx2.ConnectError("nope"),
            httpx2.Response(503),
            httpx2.Response(200, json={"ok": True}),
        ]
    )
    async with await _client(cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_mixed_retries_exhaust_budget():
    # max_attempts=2: ConnectError (attempt 1, retried) → 503 (attempt 2, terminal).
    # Budget exhausted; final 503 surfaces (transport returns it; wrapper would map to ServerError).
    cfg = RetryConfig(max_attempts=2, backoff_base=0.0)
    route = respx.get("https://test.local/health").mock(
        side_effect=[
            httpx2.ConnectError("nope"),
            httpx2.Response(503),
        ]
    )
    async with await _client(cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_retries_a_network_error_raised_by_httpx2():
    """The transport catches the stack the SDK runs on (#141).

    A ``TransportError`` from httpx2 is not an ``httpx2.TransportError``, so a
    transport still catching httpx's class lets the first failure through.
    """
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx2.ConnectError("refused", request=request)
        return httpx2.Response(200, json={"ok": True})

    transport = RetryTransport(
        httpx2.MockTransport(handler), RetryConfig(max_attempts=3, backoff_base=0.0)
    )
    async with httpx2.AsyncClient(base_url="https://test.local", transport=transport) as c:
        r = await c.get("/health")
    assert r.json() == {"ok": True}
    assert calls == 2
    assert isinstance(transport, httpx2.AsyncBaseTransport)
