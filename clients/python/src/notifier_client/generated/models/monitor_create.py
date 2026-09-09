from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MonitorCreate")


@_attrs_define
class MonitorCreate:
    """Request body for POST /monitors.

    ``interval_seconds`` is the cadence the consumer promises; a check-in is
    only late once ``grace_seconds`` on top of it has also passed.

        Attributes:
            interval_seconds (int):
            name (str):
            body_template (None | str | Unset):
            channel_ids (list[str] | Unset):
            enabled (bool | Unset):  Default: True.
            grace_seconds (int | Unset):  Default: 0.
            renotify_seconds (int | None | Unset):
            template_id (None | str | Unset):
            title_template (None | str | Unset):
    """

    interval_seconds: int
    name: str
    body_template: None | str | Unset = UNSET
    channel_ids: list[str] | Unset = UNSET
    enabled: bool | Unset = True
    grace_seconds: int | Unset = 0
    renotify_seconds: int | None | Unset = UNSET
    template_id: None | str | Unset = UNSET
    title_template: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        interval_seconds = self.interval_seconds

        name = self.name

        body_template: None | str | Unset
        if isinstance(self.body_template, Unset):
            body_template = UNSET
        else:
            body_template = self.body_template

        channel_ids: list[str] | Unset = UNSET
        if not isinstance(self.channel_ids, Unset):
            channel_ids = self.channel_ids

        enabled = self.enabled

        grace_seconds = self.grace_seconds

        renotify_seconds: int | None | Unset
        if isinstance(self.renotify_seconds, Unset):
            renotify_seconds = UNSET
        else:
            renotify_seconds = self.renotify_seconds

        template_id: None | str | Unset
        if isinstance(self.template_id, Unset):
            template_id = UNSET
        else:
            template_id = self.template_id

        title_template: None | str | Unset
        if isinstance(self.title_template, Unset):
            title_template = UNSET
        else:
            title_template = self.title_template

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "interval_seconds": interval_seconds,
                "name": name,
            }
        )
        if body_template is not UNSET:
            field_dict["body_template"] = body_template
        if channel_ids is not UNSET:
            field_dict["channel_ids"] = channel_ids
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if grace_seconds is not UNSET:
            field_dict["grace_seconds"] = grace_seconds
        if renotify_seconds is not UNSET:
            field_dict["renotify_seconds"] = renotify_seconds
        if template_id is not UNSET:
            field_dict["template_id"] = template_id
        if title_template is not UNSET:
            field_dict["title_template"] = title_template

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        interval_seconds = d.pop("interval_seconds")

        name = d.pop("name")

        def _parse_body_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        body_template = _parse_body_template(d.pop("body_template", UNSET))

        channel_ids = cast(list[str], d.pop("channel_ids", UNSET))

        enabled = d.pop("enabled", UNSET)

        grace_seconds = d.pop("grace_seconds", UNSET)

        def _parse_renotify_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        renotify_seconds = _parse_renotify_seconds(d.pop("renotify_seconds", UNSET))

        def _parse_template_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        template_id = _parse_template_id(d.pop("template_id", UNSET))

        def _parse_title_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title_template = _parse_title_template(d.pop("title_template", UNSET))

        monitor_create = cls(
            interval_seconds=interval_seconds,
            name=name,
            body_template=body_template,
            channel_ids=channel_ids,
            enabled=enabled,
            grace_seconds=grace_seconds,
            renotify_seconds=renotify_seconds,
            template_id=template_id,
            title_template=title_template,
        )

        monitor_create.additional_properties = d
        return monitor_create

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
