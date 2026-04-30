from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.plugin_detail_tokens import PluginDetailTokens
    from ..models.plugin_variant import PluginVariant


T = TypeVar("T", bound="PluginDetail")


@_attrs_define
class PluginDetail:
    """Full plugin detail including token definitions and variants.

    Attributes:
        plugin_schema (str):
        service_name (str):
        tokens (PluginDetailTokens):
        variants (list[PluginVariant]):
        service_url (None | str | Unset):
        setup_url (None | str | Unset):
    """

    plugin_schema: str
    service_name: str
    tokens: PluginDetailTokens
    variants: list[PluginVariant]
    service_url: None | str | Unset = UNSET
    setup_url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        plugin_schema = self.plugin_schema

        service_name = self.service_name

        tokens = self.tokens.to_dict()

        variants = []
        for variants_item_data in self.variants:
            variants_item = variants_item_data.to_dict()
            variants.append(variants_item)

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
                "tokens": tokens,
                "variants": variants,
            }
        )
        if service_url is not UNSET:
            field_dict["service_url"] = service_url
        if setup_url is not UNSET:
            field_dict["setup_url"] = setup_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.plugin_detail_tokens import PluginDetailTokens
        from ..models.plugin_variant import PluginVariant

        d = dict(src_dict)
        plugin_schema = d.pop("plugin_schema")

        service_name = d.pop("service_name")

        tokens = PluginDetailTokens.from_dict(d.pop("tokens"))

        variants = []
        _variants = d.pop("variants")
        for variants_item_data in _variants:
            variants_item = PluginVariant.from_dict(variants_item_data)

            variants.append(variants_item)

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

        plugin_detail = cls(
            plugin_schema=plugin_schema,
            service_name=service_name,
            tokens=tokens,
            variants=variants,
            service_url=service_url,
            setup_url=setup_url,
        )

        plugin_detail.additional_properties = d
        return plugin_detail

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
