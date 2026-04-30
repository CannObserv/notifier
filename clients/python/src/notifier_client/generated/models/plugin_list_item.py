from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="PluginListItem")


@_attrs_define
class PluginListItem:
    """Summary item for the plugin list endpoint.

    Attributes:
        plugin_schema (str):
        service_name (str):
        category (None | str | Unset):
        service_url (None | str | Unset):
        setup_url (None | str | Unset):
    """

    plugin_schema: str
    service_name: str
    category: None | str | Unset = UNSET
    service_url: None | str | Unset = UNSET
    setup_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plugin_schema = self.plugin_schema

        service_name = self.service_name

        category: None | str | Unset
        if isinstance(self.category, Unset):
            category = UNSET
        else:
            category = self.category

        service_url: None | str | Unset
        if isinstance(self.service_url, Unset):
            service_url = UNSET
        else:
            service_url = self.service_url

        setup_url: None | str | Unset
        if isinstance(self.setup_url, Unset):
            setup_url = UNSET
        else:
            setup_url = self.setup_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "plugin_schema": plugin_schema,
                "service_name": service_name,
            }
        )
        if category is not UNSET:
            field_dict["category"] = category
        if service_url is not UNSET:
            field_dict["service_url"] = service_url
        if setup_url is not UNSET:
            field_dict["setup_url"] = setup_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        plugin_schema = d.pop("plugin_schema")

        service_name = d.pop("service_name")

        def _parse_category(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        category = _parse_category(d.pop("category", UNSET))

        def _parse_service_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        service_url = _parse_service_url(d.pop("service_url", UNSET))

        def _parse_setup_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        setup_url = _parse_setup_url(d.pop("setup_url", UNSET))

        plugin_list_item = cls(
            plugin_schema=plugin_schema,
            service_name=service_name,
            category=category,
            service_url=service_url,
            setup_url=setup_url,
        )

        plugin_list_item.additional_properties = d
        return plugin_list_item

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
