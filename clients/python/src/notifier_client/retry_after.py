"""Parse the HTTP ``Retry-After`` header (RFC 9110 §10.2.3).

Accepts either a delta-seconds value (``"30"``) or an HTTP-date
(``"Wed, 21 Oct 2026 07:28:00 GMT"``). Returns the number of seconds the
caller should wait, or ``None`` if the value is missing or unparseable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    # delta-seconds path
    try:
        seconds = float(raw)
    except ValueError:
        seconds = None
    if seconds is not None:
        return max(0.0, seconds)
    # HTTP-date path
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (dt - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)
