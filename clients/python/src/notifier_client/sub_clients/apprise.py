"""``client.apprise.*`` — plugin catalog + URL assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from notifier_client.errors import error_from_response
from notifier_client.types import AssembleResponse, PluginDetail, PluginListItem

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class AppriseAPI:
    """Plugin catalog + URL assembly under ``/api/v1/apprise``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list_plugins(self) -> list[PluginListItem]:
        """GET /api/v1/apprise/plugins — plugin catalog."""
        response = await self._client._http.request(
            "GET", "/api/v1/apprise/plugins",
        )
        if response.status_code >= 400:
            raise error_from_response(response)
        return [PluginListItem.from_dict(item) for item in response.json()]

    async def get_plugin(self, schema: str) -> PluginDetail:
        """GET /api/v1/apprise/plugins/{schema} — full plugin detail."""
        return await self._client._typed_request(
            "GET", f"/api/v1/apprise/plugins/{schema}",
            model=PluginDetail, retry_safe=True,
        )

    async def assemble(
        self, schema: str, *, tokens: dict[str, Any], variant_index: int | None = None,
    ) -> AssembleResponse:
        """POST /api/v1/apprise/plugins/{schema}/assemble — build a URL from tokens."""
        body: dict[str, Any] = {"tokens": tokens}
        if variant_index is not None:
            body["variant_index"] = variant_index
        return await self._client._typed_request(
            "POST", f"/api/v1/apprise/plugins/{schema}/assemble",
            model=AssembleResponse, json=body, retry_safe=False,
        )
