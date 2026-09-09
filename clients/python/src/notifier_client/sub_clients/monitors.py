"""``client.monitors.*`` — dead-man's-timer CRUD and check-in (#56).

:meth:`MonitorsAPI.checkin` is the method a consumer calls on a schedule. Call
it **every tick, findings or not**: notifier alerts on the absence of a
check-in, so a probe that only speaks up when something is wrong is silent in
exactly the cases that matter — a stopped timer, a wedged process, a dead node.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from notifier_client.errors import error_from_response
from notifier_client.generated.models.checkin_request import CheckinRequest
from notifier_client.generated.models.checkin_request_metadata import CheckinRequestMetadata
from notifier_client.generated.models.checkin_request_status import CheckinRequestStatus
from notifier_client.generated.models.checkin_request_variables import CheckinRequestVariables
from notifier_client.generated.models.monitor_create import MonitorCreate
from notifier_client.generated.models.monitor_update import MonitorUpdate
from notifier_client.generated.types import UNSET, Unset
from notifier_client.types import CheckinResponse, MonitorOut

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class MonitorsAPI:
    """Monitor CRUD + check-in under ``/api/v1/monitors``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list(self) -> list[MonitorOut]:
        """GET /api/v1/monitors — all monitors owned by the calling tenant."""
        response = await self._client._http.request("GET", "/api/v1/monitors")
        if response.status_code >= 400:
            raise error_from_response(response)
        return [MonitorOut.from_dict(item) for item in response.json()]

    async def create(
        self,
        *,
        name: str,
        interval_seconds: int,
        grace_seconds: int | Unset = UNSET,
        renotify_seconds: int | None | Unset = UNSET,
        channel_ids: list[str] | Unset = UNSET,
        template_id: str | None | Unset = UNSET,
        title_template: str | None | Unset = UNSET,
        body_template: str | None | Unset = UNSET,
        enabled: bool | Unset = UNSET,
    ) -> MonitorOut:
        """POST /api/v1/monitors — start a dead-man's timer.

        ``interval_seconds`` is the cadence you promise to check in at;
        silence only becomes an alert once ``grace_seconds`` on top of it has
        also passed. Supply either ``template_id`` or both inline templates —
        they render a check-in that reports findings.
        """
        body = MonitorCreate(
            name=name,
            interval_seconds=interval_seconds,
            grace_seconds=grace_seconds,
            renotify_seconds=renotify_seconds,
            channel_ids=channel_ids,
            template_id=template_id,
            title_template=title_template,
            body_template=body_template,
            enabled=enabled,
        ).to_dict()
        return await self._client._typed_request(
            "POST",
            "/api/v1/monitors",
            model=MonitorOut,
            json=body,
            retry_safe=False,
        )

    async def get(self, monitor_id: str) -> MonitorOut:
        """GET /api/v1/monitors/{id} — including ``next_deadline_at``."""
        return await self._client._typed_request(
            "GET",
            f"/api/v1/monitors/{monitor_id}",
            model=MonitorOut,
            retry_safe=True,
        )

    async def update(
        self,
        monitor_id: str,
        *,
        name: str | Unset = UNSET,
        interval_seconds: int | Unset = UNSET,
        grace_seconds: int | Unset = UNSET,
        renotify_seconds: int | None | Unset = UNSET,
        channel_ids: list[str] | Unset = UNSET,
        template_id: str | None | Unset = UNSET,
        title_template: str | None | Unset = UNSET,
        body_template: str | None | Unset = UNSET,
        enabled: bool | Unset = UNSET,
    ) -> MonitorOut:
        """PATCH /api/v1/monitors/{id} — only supplied fields are sent.

        ``enabled=False`` pauses the timer for planned downtime without
        destroying the configuration.
        """
        body = MonitorUpdate(
            name=name,
            interval_seconds=interval_seconds,
            grace_seconds=grace_seconds,
            renotify_seconds=renotify_seconds,
            channel_ids=channel_ids,
            template_id=template_id,
            title_template=title_template,
            body_template=body_template,
            enabled=enabled,
        ).to_dict()
        return await self._client._typed_request(
            "PATCH",
            f"/api/v1/monitors/{monitor_id}",
            model=MonitorOut,
            json=body,
            retry_safe=False,
        )

    async def delete(self, monitor_id: str) -> None:
        """DELETE /api/v1/monitors/{id}; 204 on success.

        Not auto-retried — a 5xx may have already deleted the row, and the
        retry would 404.
        """
        response = await self._client._http.request(
            "DELETE",
            f"/api/v1/monitors/{monitor_id}",
            extensions={"notifier_no_retry": True},
        )
        if response.status_code >= 400:
            raise error_from_response(response)

    async def checkin(
        self,
        monitor_id: str,
        *,
        status: Literal["ok", "alert"] = "ok",
        variables: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CheckinResponse:
        """POST /api/v1/monitors/{id}/checkin — report in.

        Call this on every tick of your probe, whether or not it found
        anything. ``status="alert"`` additionally renders the monitor's
        template against ``variables`` and dispatches it; ``"ok"`` just resets
        the timer. ``variables`` is opaque to notifier — put your own report
        shape in it.

        Retried on transport and 5xx failures, unlike the other write methods:
        a dropped check-in is indistinguishable from a dead consumer, and a
        replay is harmless because the second check-in simply overwrites the
        first.
        """
        body = CheckinRequest(
            status=CheckinRequestStatus(status),
            variables=(
                CheckinRequestVariables.from_dict(variables) if variables is not None else UNSET
            ),
            metadata=CheckinRequestMetadata.from_dict(metadata) if metadata is not None else UNSET,
        ).to_dict()
        return await self._client._typed_request(
            "POST",
            f"/api/v1/monitors/{monitor_id}/checkin",
            model=CheckinResponse,
            json=body,
            retry_safe=True,
        )
