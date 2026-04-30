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
    retry_on_network_error: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not isinstance(self.retry_on, frozenset):
            object.__setattr__(self, "retry_on", frozenset(self.retry_on))


class RetryTransport(httpx.AsyncBaseTransport):
    """Wraps an inner transport with retry semantics."""

    def __init__(self, inner: httpx.AsyncBaseTransport, config: RetryConfig) -> None:
        self._inner = inner
        self._config = config

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Send ``request`` through the inner transport with retry semantics.

        Retries on ``cfg.retry_on`` status codes (5xx by default), on 429 when
        ``cfg.honor_retry_after`` is set, and on ``httpx.TransportError`` (network
        failures, timeouts) when ``cfg.retry_on_network_error`` is set. Backoff is
        exponential from ``cfg.backoff_base``; for 429 the ``Retry-After`` header
        wins when present.

        Per-request opt-out: callers can set ``extensions={"notifier_no_retry": True}``
        on the request to bypass the retry loop for a single call. Used by the
        wrapper to skip retries on ``POST /dispatch`` without an idempotency key.

        The transport never raises notifier-typed errors; it returns the final
        response (or re-raises the final ``httpx.TransportError`` on exhaustion).

        Note: relies on the request body being a re-readable buffer, which is
        true for ``client.request(json=...)``. Streaming bodies would be consumed
        on the first attempt and silently send empty payloads on retries.
        """
        # The request body must be re-readable across attempts.
        if request.extensions.get("notifier_no_retry"):
            return await self._inner.handle_async_request(request)
        cfg = self._config
        last: httpx.Response | None = None
        for attempt in range(1, cfg.max_attempts + 1):
            try:
                response = await self._inner.handle_async_request(request)
            except httpx.TransportError:
                if cfg.retry_on_network_error and attempt < cfg.max_attempts:
                    sleep_for = cfg.backoff_base * (2 ** (attempt - 1))
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
                    continue
                raise
            last = response
            should_retry, sleep_for = self._should_retry(response, attempt)
            if not should_retry:
                return response
            await response.aclose()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        assert last is not None
        return last

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
