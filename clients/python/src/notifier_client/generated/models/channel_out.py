from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="ChannelOut")


@_attrs_define
class ChannelOut:
    """Response body for any channel endpoint.

    The Apprise URL is never returned — only its masked prefix.

        Attributes:
            apprise_url_masked (str):
            created_at (datetime.datetime):
            id (str):
            name (str):
            tenant_id (str):
            updated_at (datetime.datetime):
            channel_hint (None | str | Unset):
    """

    apprise_url_masked: str
    created_at: datetime.datetime
    id: str
    name: str
    tenant_id: str
    updated_at: datetime.datetime
    channel_hint: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        apprise_url_masked = self.apprise_url_masked

        created_at = self.created_at.isoformat()

        id = self.id

        name = self.name

        tenant_id = self.tenant_id

        updated_at = self.updated_at.isoformat()

        channel_hint: None | str | Unset
        if isinstance(self.channel_hint, Unset):
            channel_hint = UNSET
        else:
            channel_hint = self.channel_hint

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "apprise_url_masked": apprise_url_masked,
                "created_at": created_at,
                "id": id,
                "name": name,
                "tenant_id": tenant_id,
                "updated_at": updated_at,
            }
        )
        if channel_hint is not UNSET:
            field_dict["channel_hint"] = channel_hint

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        apprise_url_masked = d.pop("apprise_url_masked")

        created_at = isoparse(d.pop("created_at"))

        id = d.pop("id")

        name = d.pop("name")

        tenant_id = d.pop("tenant_id")

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_channel_hint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        channel_hint = _parse_channel_hint(d.pop("channel_hint", UNSET))

        channel_out = cls(
            apprise_url_masked=apprise_url_masked,
            created_at=created_at,
            id=id,
            name=name,
            tenant_id=tenant_id,
            updated_at=updated_at,
            channel_hint=channel_hint,
        )

        channel_out.additional_properties = d
        return channel_out

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
