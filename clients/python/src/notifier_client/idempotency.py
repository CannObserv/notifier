"""Idempotency-key helper.

The SDK lets callers pass:
- ``None`` — omit the header (UNSAFE under retry; the SDK never auto-retries
  ``POST /dispatch`` without a key)
- a string — passthrough
- ``AUTO`` sentinel — SDK generates a ULID

ULID is preferred over UUID for sortable, URL-safe, monotonic keys.
"""

from __future__ import annotations

from typing import Final

from ulid import ULID


class _AutoIdempotencyKey:
    """Sentinel — see module docstring."""

    _instance: "_AutoIdempotencyKey | None" = None

    def __new__(cls) -> "_AutoIdempotencyKey":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "AUTO"


AUTO: Final = _AutoIdempotencyKey()


def resolve_idempotency_key(value: str | _AutoIdempotencyKey | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, _AutoIdempotencyKey):
        return str(ULID())
    return value
