"""``client.channels.*`` — channel CRUD + test."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notifier_client.errors import error_from_response
from notifier_client.generated.models.channel_create import ChannelCreate
from notifier_client.generated.models.channel_update import ChannelUpdate
from notifier_client.generated.types import UNSET, Unset
from notifier_client.types import ChannelOut, ChannelTestResponse

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class ChannelsAPI:
    """Channel CRUD + test under ``/api/v1/channels``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list(self) -> list[ChannelOut]:
        """GET /api/v1/channels — all channels owned by the calling tenant."""
        response = await self._client._http.request("GET", "/api/v1/channels")
        if response.status_code >= 400:
            raise error_from_response(response)
        return [ChannelOut.from_dict(item) for item in response.json()]

    async def create(
        self, *, name: str, apprise_url: str,
        channel_hint: str | None | Unset = UNSET,
    ) -> ChannelOut:
        """POST /api/v1/channels — store a new channel; URL is encrypted at rest."""
        body = ChannelCreate(
            name=name, apprise_url=apprise_url, channel_hint=channel_hint,
        ).to_dict()
        return await self._client._typed_request(
            "POST", "/api/v1/channels", model=ChannelOut, json=body, retry_safe=False,
        )

    async def get(self, channel_id: str) -> ChannelOut:
        """GET /api/v1/channels/{id}."""
        return await self._client._typed_request(
            "GET", f"/api/v1/channels/{channel_id}",
            model=ChannelOut, retry_safe=True,
        )

    async def update(
        self, channel_id: str, *,
        name: str | Unset = UNSET,
        apprise_url: str | Unset = UNSET,
        channel_hint: str | None | Unset = UNSET,
    ) -> ChannelOut:
        """PATCH /api/v1/channels/{id} — partial update; only supplied fields are sent."""
        body = ChannelUpdate(
            name=name, apprise_url=apprise_url, channel_hint=channel_hint,
        ).to_dict()
        return await self._client._typed_request(
            "PATCH", f"/api/v1/channels/{channel_id}",
            model=ChannelOut, json=body, retry_safe=False,
        )

    async def delete(self, channel_id: str) -> None:
        """DELETE /api/v1/channels/{id}; 204 on success."""
        response = await self._client._http.request(
            "DELETE", f"/api/v1/channels/{channel_id}",
        )
        if response.status_code >= 400:
            raise error_from_response(response)

    async def test(self, channel_id: str) -> ChannelTestResponse:
        """POST /api/v1/channels/{id}/test — fire a test notification."""
        return await self._client._typed_request(
            "POST", f"/api/v1/channels/{channel_id}/test",
            model=ChannelTestResponse, retry_safe=False,
        )
