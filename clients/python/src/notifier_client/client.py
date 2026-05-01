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
from typing import Any, TypeVar

import httpx

from notifier_client.errors import NotifierError, error_from_response
from notifier_client.generated.models.dispatch_request import DispatchRequest
from notifier_client.generated.models.dispatch_request_metadata import DispatchRequestMetadata
from notifier_client.generated.models.dispatch_request_variables import DispatchRequestVariables
from notifier_client.generated.models.preview_request import PreviewRequest
from notifier_client.generated.models.preview_request_variables import PreviewRequestVariables
from notifier_client.generated.models.preview_request_variables_schema_type_0 import (
    PreviewRequestVariablesSchemaType0,
)
from notifier_client.generated.types import UNSET
from notifier_client.idempotency import _AutoIdempotencyKey, resolve_idempotency_key
from notifier_client.retry import RetryConfig, RetryTransport
from notifier_client.sub_clients.apprise import AppriseAPI
from notifier_client.sub_clients.channels import ChannelsAPI
from notifier_client.sub_clients.templates import TemplatesAPI
from notifier_client.types import DispatchOut, PreviewResponse

T = TypeVar("T")


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
        self.channels = ChannelsAPI(self)
        self.templates = TemplatesAPI(self)
        self.apprise = AppriseAPI(self)

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
        # Free-form server schema; no typed model worth wrapping.
        return await self._json_request("GET", "/health", retry_safe=True)

    async def ready(self) -> dict[str, Any]:
        # Free-form server schema; no typed model worth wrapping.
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
    ) -> DispatchOut:
        """POST /api/v1/dispatch — render, validate, dispatch, log.

        Args:
            template_id: ID of a stored template. Either this or both
                ``title_template`` and ``body_template`` must be provided.
            title_template: Inline Jinja2 title template. Overrides the stored
                template's title when both are given.
            body_template: Inline Jinja2 body template. Same precedence as
                ``title_template``.
            variables: Variable bag for template rendering and JSON Schema
                validation (against the template's ``variables_schema``).
            channel_ids: Tenant-owned channel IDs to fan out to (required).
            idempotency_key: ``str`` for an explicit key, ``AUTO`` to generate a
                ULID, or ``None`` to omit. Auto-retry on transient failures only
                when this is non-None — without a key, retrying is unsafe and the
                SDK surfaces the first failure.
            metadata: Free-form consumer metadata stored alongside the dispatch.

        Returns:
            A ``DispatchOut`` (typed). ``.id``, ``.status``, ``.rendered_title``,
            ``.rendered_body``, ``.attempts`` are populated; ``.idempotency_key``
            echoes the request value (or is ``None`` if omitted).

        Raises:
            ValidationError: Server returned 422; ``.field_path`` and ``.section``
                identify the offending field.
            AuthError: 401 or 403.
            RateLimited: 429 after retries are exhausted.
            ServerError: 5xx after retries are exhausted.
            NotifierError: Any other 4xx (e.g. 404 for unknown channel/template).
        """
        resolved_key = resolve_idempotency_key(idempotency_key)
        body = DispatchRequest(
            channel_ids=channel_ids,
            template_id=template_id if template_id is not None else UNSET,
            title_template=title_template if title_template is not None else UNSET,
            body_template=body_template if body_template is not None else UNSET,
            variables=(
                DispatchRequestVariables.from_dict(variables) if variables is not None else UNSET
            ),
            metadata=DispatchRequestMetadata.from_dict(metadata) if metadata is not None else UNSET,
            idempotency_key=resolved_key if resolved_key is not None else UNSET,
        ).to_dict()
        return await self._typed_request(
            "POST", "/api/v1/dispatch", json=body,
            model=DispatchOut, retry_safe=resolved_key is not None,
        )

    async def preview(
        self, *,
        title_template: str,
        body_template: str,
        variables: dict[str, Any],
        variables_schema: dict[str, Any] | None = None,
    ) -> PreviewResponse:
        """POST /api/v1/preview — stateless inline render; never dispatches.

        Returns a PreviewResponse with either ``.title`` + ``.body`` populated
        or ``.error`` + ``.error_section`` set when rendering/validation fails.
        Both paths return HTTP 200; check ``.error is None`` to distinguish.
        No exception is raised for rendering/validation failures.
        """
        body = PreviewRequest(
            title_template=title_template,
            body_template=body_template,
            variables=PreviewRequestVariables.from_dict(variables),
            variables_schema=(
                PreviewRequestVariablesSchemaType0.from_dict(variables_schema)
                if variables_schema is not None else UNSET
            ),
        ).to_dict()
        return await self._typed_request(
            "POST", "/api/v1/preview",
            model=PreviewResponse, json=body, retry_safe=False,
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

    async def _typed_request(
        self, method: str, path: str, *, model: type[T],
        json: Any = None, retry_safe: bool,
    ) -> T:
        """Run an authed request, map errors, and parse into ``model``.

        The single funnel for all typed endpoint methods. ``model.from_dict``
        must accept the JSON body verbatim. An empty body where a typed model
        is expected indicates a server contract violation and surfaces as a
        NotifierError with the model name for diagnostics.
        """
        extensions = {} if retry_safe else {"notifier_no_retry": True}
        response = await self._http.request(method, path, json=json, extensions=extensions)
        if response.status_code >= 400:
            raise error_from_response(response)
        if not response.content:
            raise NotifierError(
                f"empty response body, expected {model.__name__}",
                status_code=response.status_code, response=response,
            )
        return model.from_dict(response.json())
