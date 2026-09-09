from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.monitor_out_state import MonitorOutState

if TYPE_CHECKING:
    from ..models.monitor_out_last_variables import MonitorOutLastVariables


T = TypeVar("T", bound="MonitorOut")


@_attrs_define
class MonitorOut:
    """Response body for the monitor CRUD endpoints.

    Attributes:
        body_template (None | str):
        channel_ids (list[str]):
        created_at (datetime.datetime):
        enabled (bool):
        grace_seconds (int):
        id (str):
        interval_seconds (int):
        last_alert_at (datetime.datetime | None):
        last_checkin_at (datetime.datetime | None):
        last_status (None | str):
        last_variables (MonitorOutLastVariables):
        name (str):
        next_deadline_at (datetime.datetime):
        renotify_seconds (int | None):
        state (MonitorOutState):
        template_id (None | str):
        tenant_id (str):
        title_template (None | str):
        updated_at (datetime.datetime):
    """

    body_template: None | str
    channel_ids: list[str]
    created_at: datetime.datetime
    enabled: bool
    grace_seconds: int
    id: str
    interval_seconds: int
    last_alert_at: datetime.datetime | None
    last_checkin_at: datetime.datetime | None
    last_status: None | str
    last_variables: MonitorOutLastVariables
    name: str
    next_deadline_at: datetime.datetime
    renotify_seconds: int | None
    state: MonitorOutState
    template_id: None | str
    tenant_id: str
    title_template: None | str
    updated_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body_template: None | str
        body_template = self.body_template

        channel_ids = self.channel_ids

        created_at = self.created_at.isoformat()

        enabled = self.enabled

        grace_seconds = self.grace_seconds

        id = self.id

        interval_seconds = self.interval_seconds

        last_alert_at: None | str
        if isinstance(self.last_alert_at, datetime.datetime):
            last_alert_at = self.last_alert_at.isoformat()
        else:
            last_alert_at = self.last_alert_at

        last_checkin_at: None | str
        if isinstance(self.last_checkin_at, datetime.datetime):
            last_checkin_at = self.last_checkin_at.isoformat()
        else:
            last_checkin_at = self.last_checkin_at

        last_status: None | str
        last_status = self.last_status

        last_variables = self.last_variables.to_dict()

        name = self.name

        next_deadline_at = self.next_deadline_at.isoformat()

        renotify_seconds: int | None
        renotify_seconds = self.renotify_seconds

        state = self.state.value

        template_id: None | str
        template_id = self.template_id

        tenant_id = self.tenant_id

        title_template: None | str
        title_template = self.title_template

        updated_at = self.updated_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "body_template": body_template,
                "channel_ids": channel_ids,
                "created_at": created_at,
                "enabled": enabled,
                "grace_seconds": grace_seconds,
                "id": id,
                "interval_seconds": interval_seconds,
                "last_alert_at": last_alert_at,
                "last_checkin_at": last_checkin_at,
                "last_status": last_status,
                "last_variables": last_variables,
                "name": name,
                "next_deadline_at": next_deadline_at,
                "renotify_seconds": renotify_seconds,
                "state": state,
                "template_id": template_id,
                "tenant_id": tenant_id,
                "title_template": title_template,
                "updated_at": updated_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.monitor_out_last_variables import MonitorOutLastVariables  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_body_template(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        body_template = _parse_body_template(d.pop("body_template"))

        channel_ids = cast(list[str], d.pop("channel_ids"))

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        enabled = d.pop("enabled")

        grace_seconds = d.pop("grace_seconds")

        id = d.pop("id")

        interval_seconds = d.pop("interval_seconds")

        def _parse_last_alert_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_alert_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_alert_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_alert_at = _parse_last_alert_at(d.pop("last_alert_at"))

        def _parse_last_checkin_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_checkin_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_checkin_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_checkin_at = _parse_last_checkin_at(d.pop("last_checkin_at"))

        def _parse_last_status(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        last_status = _parse_last_status(d.pop("last_status"))

        last_variables = MonitorOutLastVariables.from_dict(d.pop("last_variables"))

        name = d.pop("name")

        next_deadline_at = datetime.datetime.fromisoformat(d.pop("next_deadline_at"))

        def _parse_renotify_seconds(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        renotify_seconds = _parse_renotify_seconds(d.pop("renotify_seconds"))

        state = MonitorOutState(d.pop("state"))

        def _parse_template_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        template_id = _parse_template_id(d.pop("template_id"))

        tenant_id = d.pop("tenant_id")

        def _parse_title_template(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        title_template = _parse_title_template(d.pop("title_template"))

        updated_at = datetime.datetime.fromisoformat(d.pop("updated_at"))

        monitor_out = cls(
            body_template=body_template,
            channel_ids=channel_ids,
            created_at=created_at,
            enabled=enabled,
            grace_seconds=grace_seconds,
            id=id,
            interval_seconds=interval_seconds,
            last_alert_at=last_alert_at,
            last_checkin_at=last_checkin_at,
            last_status=last_status,
            last_variables=last_variables,
            name=name,
            next_deadline_at=next_deadline_at,
            renotify_seconds=renotify_seconds,
            state=state,
            template_id=template_id,
            tenant_id=tenant_id,
            title_template=title_template,
            updated_at=updated_at,
        )

        monitor_out.additional_properties = d
        return monitor_out

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
