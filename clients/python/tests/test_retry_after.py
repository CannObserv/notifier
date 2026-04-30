from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from notifier_client.retry_after import parse_retry_after


def test_parse_seconds_integer():
    assert parse_retry_after("30") == 30.0


def test_parse_seconds_float_rejected():
    # Spec says delta-seconds is an integer; float should be rejected (or accepted leniently?)
    # We accept float for ergonomics — tests the lenient path.
    assert parse_retry_after("1.5") == 1.5


def test_parse_http_date():
    # 60 seconds from now
    future = datetime.now(UTC) + timedelta(seconds=60)
    raw = format_datetime(future, usegmt=True)
    parsed = parse_retry_after(raw)
    assert parsed is not None
    assert 55 <= parsed <= 65    # tolerate clock skew + test timing


def test_parse_past_http_date_returns_zero():
    past = datetime.now(UTC) - timedelta(seconds=120)
    raw = format_datetime(past, usegmt=True)
    assert parse_retry_after(raw) == 0.0


def test_parse_none_returns_none():
    assert parse_retry_after(None) is None


def test_parse_garbage_returns_none():
    assert parse_retry_after("not a thing") is None


def test_parse_negative_returns_zero():
    assert parse_retry_after("-5") == 0.0
