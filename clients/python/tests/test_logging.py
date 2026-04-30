import logging

from notifier_client.logging import RedactingFilter


def test_filter_masks_api_key_in_message():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="auth header was nk_supersecret123 today", args=(), exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()
    assert "nk_***" in record.getMessage()


def test_filter_masks_in_args():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="key: %s", args=("nk_supersecret123",), exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()


def test_filter_no_op_when_no_key():
    flt = RedactingFilter(api_key=None)
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    assert flt.filter(record) is True
    assert record.getMessage() == "hello"
