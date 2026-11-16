import logging
from pathlib import Path

import pytest

from notifier_client import NotifierClient
from notifier_client.logging import RedactingFilter


def test_filter_masks_api_key_in_message():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="auth header was nk_supersecret123 today",
        args=(),
        exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()
    assert "nk_***" in record.getMessage()


def test_filter_masks_in_args():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="key: %s",
        args=("nk_supersecret123",),
        exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()


def test_filter_no_op_when_no_key():
    flt = RedactingFilter(api_key=None)
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert flt.filter(record) is True
    assert record.getMessage() == "hello"


README = Path(__file__).resolve().parents[1] / "README.md"


class _Seen(RedactingFilter):
    """A RedactingFilter that records what it was asked to filter."""

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        self.records: list[logging.LogRecord] = []

    def filter(self, record: logging.LogRecord) -> bool:
        self.records.append(record)
        return super().filter(record)


@pytest.mark.asyncio
async def test_the_readme_logger_is_the_one_sdk_traffic_is_logged_on(httpx2_wire, caplog):
    """A filter attached where the README says sees the SDK's requests (#141).

    httpx2 logs each request line on ``httpx2``. Under httpx it was ``httpx``,
    and a filter left on the old name is consulted for nothing.
    """
    assert 'logging.getLogger("httpx2").addFilter(RedactingFilter(' in README.read_text()
    logger = logging.getLogger("httpx2")
    seen = _Seen(api_key="nk_supersecret123")
    logger.addFilter(seen)
    caplog.set_level(logging.INFO, logger="httpx2")
    try:
        async with NotifierClient(base_url="http://127.0.0.1:9", api_key="nk_x") as c:
            await c.health()
    finally:
        logger.removeFilter(seen)
    assert [r.getMessage() for r in seen.records] == [
        'HTTP Request: GET http://127.0.0.1:9/health "HTTP/1.1 200 OK"'
    ]
