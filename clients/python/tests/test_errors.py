import httpx

from notifier_client.errors import (
    AuthError,
    NotifierError,
    RateLimited,
    ServerError,
    ValidationError,
    error_from_response,
)


def _resp(status: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, json=json_body or {})


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
    resp = httpx.Response(
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
