"""Tests for src/core/logging.py — JSON log record field contract."""

import json
import logging

from src.core.logging import configure_logging, get_logger


def test_log_record_includes_structured_fields(capsys):
    """Regression: bare JsonFormatter() emitted only {"message"} (issue #11)."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        configure_logging()
        get_logger("src.some.module").warning("hello %s", "world")
    finally:
        root.handlers, root.level = saved_handlers, saved_level

    record = json.loads(capsys.readouterr().out)
    assert record["message"] == "hello world"
    assert record["level"] == "WARNING"
    assert record["logger"] == "src.some.module"
    assert "timestamp" in record
