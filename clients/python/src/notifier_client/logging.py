"""Logging support for notifier-client.

The SDK never emits logs on its own (callers wire their own loggers), but it
provides ``RedactingFilter`` so callers who do log the SDK's underlying httpx
traffic don't accidentally leak the X-API-Key.
"""

from __future__ import annotations

import logging


class RedactingFilter(logging.Filter):
    """Filter that masks the X-API-Key value in log messages and args.

    Best-effort: only scrubs string ``record.msg`` and string entries in
    ``record.args``. Non-string ``msg`` values (e.g. an exception object passed
    via ``logger.error(exc)``) and nested structures (dicts, tuples, custom
    objects) pass through unredacted. Use this filter as a guardrail for the
    common case, not as a guaranteed redactor for every logging shape.
    """

    def __init__(self, api_key: str | None) -> None:
        super().__init__()
        self._api_key = api_key
        self._mask = (api_key[:3] + "***") if api_key else None

    def filter(self, record: logging.LogRecord) -> bool:
        if self._api_key is None or self._mask is None:
            return True
        if isinstance(record.msg, str) and self._api_key in record.msg:
            record.msg = record.msg.replace(self._api_key, self._mask)
        if record.args:
            record.args = tuple(self._scrub(a) for a in record.args)   # type: ignore[assignment]
        return True

    def _scrub(self, value):
        if isinstance(value, str) and self._api_key in value:
            return value.replace(self._api_key, self._mask)
        return value
