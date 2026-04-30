"""Typed exception hierarchy for notifier-client.

All exceptions inherit ``NotifierError``. Code that catches notifier issues
generically can catch ``NotifierError``; code that wants to react differently
to auth, validation, rate-limit, or server failures catches the specific
subclass.
"""

from __future__ import annotations

import httpx

from notifier_client.retry_after import parse_retry_after


class NotifierError(Exception):
    """Base class for all notifier-client errors."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 response: httpx.Response | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AuthError(NotifierError):
    """401 or 403 — invalid or missing API key."""


class ValidationError(NotifierError):
    """422 — request body or rendered template failed validation.

    ``section`` is one of ``"variables"``, ``"title"``, ``"body"`` (notifier's
    typed shape) or ``"body"`` for FastAPI's default validator output.
    ``field_path`` is dot-joined when notifier returns a list-style ``loc``.
    """

    def __init__(self, message: str, *, section: str | None = None,
                 field_path: str | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.section = section
        self.field_path = field_path


class RateLimited(NotifierError):
    """429 — caller exceeded rate limit. Retries are exhausted by the time this fires."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class ServerError(NotifierError):
    """5xx — server-side failure. Retried by the transport before this fires."""


def error_from_response(response: httpx.Response) -> NotifierError:
    """Map an HTTP response to the appropriate typed error."""
    status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = {}
    detail = body.get("detail") if isinstance(body, dict) else None

    if status in (401, 403):
        return AuthError(_message(detail, default="authentication failed"),
                         status_code=status, response=response)
    if status == 422:
        section, field_path, msg = _parse_validation_detail(detail)
        return ValidationError(msg, section=section, field_path=field_path,
                               status_code=status, response=response)
    if status == 429:
        return RateLimited(
            _message(detail, default="rate limited"),
            retry_after_seconds=parse_retry_after(response.headers.get("Retry-After")),
            status_code=status, response=response,
        )
    if 500 <= status < 600:
        return ServerError(_message(detail, default=f"server error {status}"),
                           status_code=status, response=response)
    return NotifierError(_message(detail, default=f"http {status}"),
                         status_code=status, response=response)


def _message(detail, *, default: str) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and "message" in detail:
        return str(detail["message"])
    return default


def _parse_validation_detail(detail) -> tuple[str | None, str | None, str]:
    """Return (section, field_path, message).

    Handles notifier's typed shape and FastAPI defaults.
    """
    if isinstance(detail, dict):
        # Notifier shape: {"section": ..., "path": ..., "message": ...}
        return (
            detail.get("section"),
            detail.get("path"),
            str(detail.get("message", "validation error")),
        )
    if isinstance(detail, list) and detail:
        # FastAPI default: [{"loc": [...], "msg": "...", "type": "..."}, ...]
        first = detail[0]
        loc = first.get("loc", []) if isinstance(first, dict) else []
        path = ".".join(str(p) for p in loc)
        return (None, path or None, str(first.get("msg", "validation error")))
    return (None, None, "validation error")
