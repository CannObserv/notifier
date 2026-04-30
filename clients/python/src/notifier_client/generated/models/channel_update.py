from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ChannelUpdate")


@_attrs_define
class ChannelUpdate:
    """Request body for PATCH /channels/{id} — all fields optional.

    Attributes:
        apprise_url (None | str | Unset):
        channel_hint (None | str | Unset):
        name (None | str | Unset):
    """

    apprise_url: None | str | Unset = UNSET
    channel_hint: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        apprise_url: None | str | Unset
        if isinstance(self.apprise_url, Unset):
            apprise_url = UNSET
        else:
            apprise_url = self.apprise_url

        channel_hint: None | str | Unset
        if isinstance(self.channel_hint, Unset):
            channel_hint = UNSET
        else:
            channel_hint = self.channel_hint

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if apprise_url is not UNSET:
            field_dict["apprise_url"] = apprise_url
        if channel_hint is not UNSET:
            field_dict["channel_hint"] = channel_hint
        if name is not UNSET:
            field_dict["name"] = name

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_apprise_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        apprise_url = _parse_apprise_url(d.pop("apprise_url", UNSET))

        def _parse_channel_hint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_hint = _parse_channel_hint(d.pop("channel_hint", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        channel_update = cls(
            apprise_url=apprise_url,
            channel_hint=channel_hint,
            name=name,
        )

        channel_update.additional_properties = d
        return channel_update

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
