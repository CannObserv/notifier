import httpx2
import pytest

from notifier_client import NotifierClient, RetryConfig
from notifier_client.errors import (
    AuthError,
    NotifierError,
    RateLimited,
    ServerError,
    ValidationError,
    error_from_response,
)


def _resp(status: int, json_body: dict | None = None) -> httpx2.Response:
    return httpx2.Response(status_code=status, json=json_body or {})


def test_auth_error_for_401():
    err = error_from_response(_resp(401, {"detail": "invalid api key"}))
    assert isinstance(err, AuthError)
    assert isinstance(err, NotifierError)
    assert err.status_code == 401


def test_auth_error_for_403():
    assert isinstance(error_from_response(_resp(403)), AuthError)


def test_validation_error_parses_field_path():
    err = error_from_response(
        _resp(422, {"detail": {"section": "variables", "path": "strain", "message": "required"}})
    )
    assert isinstance(err, ValidationError)
    assert err.field_path == "strain"
    assert err.section == "variables"
    assert "required" in str(err)


def test_validation_error_handles_pydantic_style_detail():
    # FastAPI default 422 shape: detail is a list of {loc, msg, type}
    detail = [{"loc": ["body", "channel_ids"], "msg": "field required", "type": "missing"}]
    err = error_from_response(_resp(422, {"detail": detail}))
    assert isinstance(err, ValidationError)
    assert err.field_path == "body.channel_ids"


def test_rate_limited_carries_retry_after():
    resp = httpx2.Response(
        status_code=429, headers={"Retry-After": "30"}, json={"detail": "slow down"}
    )
    err = error_from_response(resp)
    assert isinstance(err, RateLimited)
    assert err.retry_after_seconds == 30


def test_server_error_for_5xx():
    assert isinstance(error_from_response(_resp(500)), ServerError)
    assert isinstance(error_from_response(_resp(503)), ServerError)


def test_generic_notifier_error_for_other_4xx():
    err = error_from_response(_resp(404, {"detail": "not found"}))
    assert isinstance(err, NotifierError)
    assert err.status_code == 404


@pytest.mark.asyncio
async def test_a_raised_error_carries_the_httpx2_response(httpx2_wire):
    """``NotifierError.response`` is the response the SDK received — httpx2's (#141)."""
    httpx2_wire.response = httpx2.Response(401, json={"detail": "bad key"})
    async with NotifierClient(
        base_url="http://127.0.0.1:9", api_key="nk_x", retry_config=RetryConfig(max_attempts=1)
    ) as c:
        with pytest.raises(AuthError) as exc:
            await c.health()
    assert isinstance(exc.value.response, httpx2.Response)
    assert exc.value.response.status_code == 401
