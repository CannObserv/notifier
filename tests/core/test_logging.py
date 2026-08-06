"""Regression tests: JSON log records carry timestamp, level, and logger name,
and uvicorn's own loggers share the app's JSON formatter and drop uvicorn's
ANSI `color_message` extra (issues #11, #14; skills#69, skills#81, skills#82).
"""

import json
import logging
import logging.config
from pathlib import Path

from src.core.logging import (
    ColorMessageFilter,
    build_json_formatter,
    configure_logging,
    get_logger,
)

LOG_CONFIG_PATH = Path("src/core/log_config.json")


def _snapshot(names):
    """Capture mutable logger state so a dictConfig() call can be rolled back.

    dictConfig() and configure_logging() both mutate live loggers; leaking that
    into later tests is an order-dependent flake, so every attribute they touch
    is saved and restored.
    """
    saved = {}
    for name in names:
        logger = logging.getLogger(name)
        saved[name] = {
            "handlers": logger.handlers[:],
            "filters": logger.filters[:],
            "propagate": logger.propagate,
            "level": logger.level,
        }
    return saved


def _restore(saved):
    for name, attrs in saved.items():
        logger = logging.getLogger(name)
        for attr, value in attrs.items():
            setattr(logger, attr, value)


def test_log_record_includes_structured_fields(capsys):
    """Regression: bare JsonFormatter() emitted only {"message"} (issue #11)."""
    saved = _snapshot(("",))  # "" is the root logger — configure_logging() rebinds it
    try:
        configure_logging()
        get_logger("src.some.module").warning("hello %s", "world")
    finally:
        _restore(saved)

    record = json.loads(capsys.readouterr().out)
    assert record["message"] == "hello world"
    assert record["level"] == "WARNING"
    assert record["logger"] == "src.some.module"
    assert "timestamp" in record


def test_uvicorn_log_config_is_valid_and_shares_formatter():
    """The uvicorn --log-config file wires uvicorn's loggers through the same
    formatter as the app, and dictConfig accepts it (a malformed file would
    fail the service at boot, not in review)."""
    config = json.loads(LOG_CONFIG_PATH.read_text())

    # Single source of truth: the file builds its formatter from the factory
    # configure_logging() also uses, not a duplicated fmt string.
    assert any(
        f.get("()") == "src.core.logging.build_json_formatter"
        for f in config["formatters"].values()
    )
    # All three uvicorn loggers must be present, else they keep the plain
    # default — and each must carry the color_message strip. Asserting
    # placement, not just effect: moving the filter to the stdout handler still
    # produces clean JSON today, and that is the variant that breaks silently
    # under a sink reading record.__dict__ directly (skills#82).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert name in config["loggers"]
        assert "strip_color_message" in config["loggers"][name]["filters"]

    saved = _snapshot(("", "uvicorn", "uvicorn.error", "uvicorn.access"))
    try:
        logging.config.dictConfig(config)  # raises on a malformed config
    finally:
        _restore(saved)


def test_shared_formatter_renders_uvicorn_access_record():
    """A uvicorn.access record formats to JSON with the same fields as app logs
    — the request line lands in `message`, not a plain-text handler."""
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:0", "GET", "/health", "1.1", 200),
        exc_info=None,
    )
    parsed = json.loads(build_json_formatter().format(record))
    assert parsed["logger"] == "uvicorn.access"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == '127.0.0.1:0 - "GET /health HTTP/1.1" 200'
    assert "timestamp" in parsed


def test_color_message_filter_strips_extra_at_the_record_source():
    """uvicorn's ANSI-duplicate `color_message` extra never reaches a payload.

    Asserts on the record itself, not only the rendered JSON: the strip has to
    hold for any sink, including handlers that read `record.__dict__` directly
    rather than going through a `logging.Formatter` (skills#82).
    """
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Started server process [%d]",
        args=(4066888,),
        exc_info=None,
    )
    record.color_message = "Started server process [\x1b[36m%d\x1b[0m]"

    assert ColorMessageFilter().filter(record) is True  # never drops a record
    assert not hasattr(record, "color_message")

    parsed = json.loads(build_json_formatter().format(record))
    assert "color_message" not in parsed
    assert parsed["message"] == "Started server process [4066888]"
