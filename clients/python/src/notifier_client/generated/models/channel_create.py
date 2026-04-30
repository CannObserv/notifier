from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ChannelCreate")


@_attrs_define
class ChannelCreate:
    """Request body for POST /channels.

    Attributes:
        apprise_url (str):
        name (str):
        channel_hint (None | str | Unset):
    """

    apprise_url: str
    name: str
    channel_hint: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        apprise_url = self.apprise_url

        name = self.name

        channel_hint: None | str | Unset
        if isinstance(self.channel_hint, Unset):
            channel_hint = UNSET
        else:
            channel_hint = self.channel_hint

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "apprise_url": apprise_url,
                "name": name,
            }
        )
        if channel_hint is not UNSET:
            field_dict["channel_hint"] = channel_hint

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        apprise_url = d.pop("apprise_url")

        name = d.pop("name")

        def _parse_channel_hint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_hint = _parse_channel_hint(d.pop("channel_hint", UNSET))

        channel_create = cls(
            apprise_url=apprise_url,
            name=name,
            channel_hint=channel_hint,
        )

        channel_create.additional_properties = d
        return channel_create

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
