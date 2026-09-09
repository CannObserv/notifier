from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MonitorUpdate")


@_attrs_define
class MonitorUpdate:
    """Request body for PATCH /monitors/{id}. Every field optional.

    Attributes:
        body_template (None | str | Unset):
        channel_ids (list[str] | None | Unset):
        enabled (bool | None | Unset):
        grace_seconds (int | None | Unset):
        interval_seconds (int | None | Unset):
        name (None | str | Unset):
        renotify_seconds (int | None | Unset):
        template_id (None | str | Unset):
        title_template (None | str | Unset):
    """

    body_template: None | str | Unset = UNSET
    channel_ids: list[str] | None | Unset = UNSET
    enabled: bool | None | Unset = UNSET
    grace_seconds: int | None | Unset = UNSET
    interval_seconds: int | None | Unset = UNSET
    name: None | str | Unset = UNSET
    renotify_seconds: int | None | Unset = UNSET
    template_id: None | str | Unset = UNSET
    title_template: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body_template: None | str | Unset
        if isinstance(self.body_template, Unset):
            body_template = UNSET
        else:
            body_template = self.body_template

        channel_ids: list[str] | None | Unset
        if isinstance(self.channel_ids, Unset):
            channel_ids = UNSET
        elif isinstance(self.channel_ids, list):
            channel_ids = self.channel_ids

        else:
            channel_ids = self.channel_ids

        enabled: bool | None | Unset
        if isinstance(self.enabled, Unset):
            enabled = UNSET
        else:
            enabled = self.enabled

        grace_seconds: int | None | Unset
        if isinstance(self.grace_seconds, Unset):
            grace_seconds = UNSET
        else:
            grace_seconds = self.grace_seconds

        interval_seconds: int | None | Unset
        if isinstance(self.interval_seconds, Unset):
            interval_seconds = UNSET
        else:
            interval_seconds = self.interval_seconds

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

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
        field_dict.update({})
        if body_template is not UNSET:
            field_dict["body_template"] = body_template
        if channel_ids is not UNSET:
            field_dict["channel_ids"] = channel_ids
        if enabled is not UNSET:
            field_dict["enabled"] = enabled
        if grace_seconds is not UNSET:
            field_dict["grace_seconds"] = grace_seconds
        if interval_seconds is not UNSET:
            field_dict["interval_seconds"] = interval_seconds
        if name is not UNSET:
            field_dict["name"] = name
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

        def _parse_body_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        body_template = _parse_body_template(d.pop("body_template", UNSET))

        def _parse_channel_ids(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                channel_ids_type_0 = cast(list[str], data)

                return channel_ids_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        channel_ids = _parse_channel_ids(d.pop("channel_ids", UNSET))

        def _parse_enabled(data: object) -> bool | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(bool | None | Unset, data)

        enabled = _parse_enabled(d.pop("enabled", UNSET))

        def _parse_grace_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        grace_seconds = _parse_grace_seconds(d.pop("grace_seconds", UNSET))

        def _parse_interval_seconds(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        interval_seconds = _parse_interval_seconds(d.pop("interval_seconds", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

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

        monitor_update = cls(
            body_template=body_template,
            channel_ids=channel_ids,
            enabled=enabled,
            grace_seconds=grace_seconds,
            interval_seconds=interval_seconds,
            name=name,
            renotify_seconds=renotify_seconds,
            template_id=template_id,
            title_template=title_template,
        )

        monitor_update.additional_properties = d
        return monitor_update

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
