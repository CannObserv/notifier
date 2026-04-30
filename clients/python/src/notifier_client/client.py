"""``NotifierClient`` — the public facade.

Composes the generated client (for typed models) with our own httpx layer
(for retries, auth, error mapping). We do *not* subclass anything in
``generated/`` — codegen renames internals between versions of
``openapi-python-client``.

The client is async-only. A sync facade is not in scope; if you need one,
file an issue with a use case.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from notifier_client.errors import error_from_response
from notifier_client.idempotency import _AutoIdempotencyKey, resolve_idempotency_key
from notifier_client.retry import RetryConfig, RetryTransport


class NotifierClient:
    """Async client for the notifier service."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        retry_config: RetryConfig | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._retry_config = retry_config or RetryConfig()
        self._mask = (api_key[:3] + "***") if api_key else "***"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            transport=RetryTransport(httpx.AsyncHTTPTransport(), self._retry_config),
        )

    def __repr__(self) -> str:
        return f"NotifierClient(base_url={self._base_url!r}, api_key={self._mask!r})"

    async def __aenter__(self) -> NotifierClient:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None,
                        exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- endpoints ---

    async def health(self) -> dict[str, Any]:
        return await self._json_request("GET", "/health", retry_safe=True)

    async def ready(self) -> dict[str, Any]:
        return await self._json_request("GET", "/ready", retry_safe=True)

    async def dispatch(
        self,
        *,
        template_id: str | None = None,
        title_template: str | None = None,
        body_template: str | None = None,
        variables: dict[str, Any] | None = None,
        channel_ids: list[str],
        idempotency_key: str | _AutoIdempotencyKey | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/dispatch.

        Auto-retries are only attempted when ``idempotency_key`` is non-None
        (including ``AUTO``). Without a key, retrying is unsafe and the SDK
        will surface the first failure.
        """
        resolved_key = resolve_idempotency_key(idempotency_key)
        body: dict[str, Any] = {
            "channel_ids": channel_ids,
            "variables": variables or {},
            "metadata": metadata or {},
        }
        if template_id is not None:
            body["template_id"] = template_id
        if title_template is not None:
            body["title_template"] = title_template
        if body_template is not None:
            body["body_template"] = body_template
        if resolved_key is not None:
            body["idempotency_key"] = resolved_key
        return await self._json_request(
            "POST", "/api/v1/dispatch", json=body,
            retry_safe=resolved_key is not None,
        )

    # --- internals ---

    async def _json_request(
        self, method: str, path: str, *, json: Any = None, retry_safe: bool,
    ) -> dict[str, Any]:
        extensions = {} if retry_safe else {"notifier_no_retry": True}
        response = await self._http.request(method, path, json=json, extensions=extensions)
        if response.status_code >= 400:
            raise error_from_response(response)
        if not response.content:
            return {}
        return response.json()
