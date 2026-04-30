"""Retry transport for httpx — retries on 5xx + 429 with exponential backoff.

The transport itself never raises notifier-typed errors. It returns the final
HTTP response (success or terminal failure); the calling wrapper translates
non-2xx responses into typed errors at the boundary.

Why a transport (not an event hook): transports give us full control over the
request lifecycle, including streaming response bodies and cancellation. Hooks
are awkward for retries because they fire after the response is consumed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from notifier_client.retry_after import parse_retry_after


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    backoff_base: float = 0.5
    retry_on: frozenset[int] = field(default_factory=lambda: frozenset({500, 502, 503, 504}))
    honor_retry_after: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.retry_on, frozenset):
            object.__setattr__(self, "retry_on", frozenset(self.retry_on))


class RetryTransport(httpx.AsyncBaseTransport):
    """Wraps an inner transport with retry semantics."""

    def __init__(self, inner: httpx.AsyncBaseTransport, config: RetryConfig) -> None:
        self._inner = inner
        self._config = config

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Per-request opt-out: callers signal "do not retry this one" via extensions.
        # Used by NotifierClient to skip retries on POST /dispatch without an idempotency key.
        if request.extensions.get("notifier_no_retry"):
            return await self._inner.handle_async_request(request)
        cfg = self._config
        last: httpx.Response | None = None
        for attempt in range(1, cfg.max_attempts + 1):
            response = await self._inner.handle_async_request(request)
            last = response
            should_retry, sleep_for = self._should_retry(response, attempt)
            if not should_retry:
                return response
            await response.aclose()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        return last  # type: ignore[return-value]

    def _should_retry(self, response: httpx.Response, attempt: int) -> tuple[bool, float]:
        cfg = self._config
        if attempt >= cfg.max_attempts:
            return (False, 0.0)
        status = response.status_code
        if status in cfg.retry_on:
            return (True, cfg.backoff_base * (2 ** (attempt - 1)))
        if status == 429 and cfg.honor_retry_after:
            wait = parse_retry_after(response.headers.get("Retry-After"))
            return (True, wait if wait is not None else cfg.backoff_base * (2 ** (attempt - 1)))
        return (False, 0.0)

    async def aclose(self) -> None:
        await self._inner.aclose()
