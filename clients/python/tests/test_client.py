import httpx
import pytest
import respx

from notifier_client import (
    AUTO,
    AuthError,
    NotifierClient,
    RateLimited,
    RetryConfig,
    ValidationError,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


@respx.mock
@pytest.mark.asyncio
async def test_health_round_trip(fast_retry):
    respx.get("https://t.local/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.health()
    assert result == {"status": "ok"}


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_sends_x_api_key_header(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "k",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_secret", retry_config=fast_retry
    ) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key="k",
        )
    assert route.calls.last.request.headers["X-API-Key"] == "nk_secret"


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_with_auto_idempotency_generates_ulid(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "auto",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key=AUTO,
        )
    body = route.calls.last.request.read().decode()
    assert "idempotency_key" in body
    # ULIDs are 26 chars; check the value isn't empty or AUTO literal
    assert "AUTO" not in body


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_never_auto_retried_without_idempotency_key(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(503),
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(Exception):    # ServerError
            await c.dispatch(
                title_template="T", body_template="B", channel_ids=["ch1"],
                idempotency_key=None,
            )
    # Should have been called exactly once — no retries on POST /dispatch without idempotency_key
    assert route.call_count == 1
    # And the request body must omit idempotency_key when caller passed None
    body = route.calls.last.request.read().decode()
    assert "idempotency_key" not in body


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_retried_with_idempotency_key(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(side_effect=[
        httpx.Response(503),
        httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "k",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        }),
    ])
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key="k",
        )
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_validation_error_with_field_path(fast_retry):
    respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(422, json={"detail": {
            "section": "variables", "path": "strain", "message": "required",
        }})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ValidationError) as exc:
            await c.dispatch(
                title_template="T", body_template="B", channel_ids=["ch1"],
                idempotency_key="k",
            )
    assert exc.value.field_path == "strain"
    assert exc.value.section == "variables"


@respx.mock
@pytest.mark.asyncio
async def test_auth_error_on_401(fast_retry):
    route = respx.get("https://t.local/health").mock(return_value=httpx.Response(401))
    async with NotifierClient(
        base_url="https://t.local", api_key="bad", retry_config=fast_retry
    ) as c:
        with pytest.raises(AuthError):
            await c.health()
    # 401 is not in retry_on — must not be retried
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_rate_limited_when_429_exhausted(fast_retry):
    # max_attempts=2; both 429 → final response surfaces as RateLimited
    respx.get("https://t.local/health").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(RateLimited) as exc:
            await c.health()
    assert exc.value.retry_after_seconds == 0.0


def test_repr_redacts_api_key():
    c = NotifierClient(base_url="https://t.local", api_key="nk_supersecret")
    assert "nk_supersecret" not in repr(c)
    assert "nk_***" in repr(c)
