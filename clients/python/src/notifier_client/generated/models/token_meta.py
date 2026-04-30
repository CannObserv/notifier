from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="TokenMeta")


@_attrs_define
class TokenMeta:
    """Metadata for a single Apprise plugin token.

    Attributes:
        name (str):
        private (bool):
        required (bool):
        type_ (str):
        default (Any | Unset):
        regex (None | str | Unset):
        values (list[str] | None | Unset):
    """

    name: str
    private: bool
    required: bool
    type_: str
    default: Any | Unset = UNSET
    regex: None | str | Unset = UNSET
    values: list[str] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        private = self.private

        required = self.required

        type_ = self.type_

        default = self.default

        regex: None | str | Unset
        if isinstance(self.regex, Unset):
            regex = UNSET
        else:
            regex = self.regex

        values: list[str] | None | Unset
        if isinstance(self.values, Unset):
            values = UNSET
        elif isinstance(self.values, list):
            values = self.values

        else:
            values = self.values

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "private": private,
                "required": required,
                "type": type_,
            }
        )
        if default is not UNSET:
            field_dict["default"] = default
        if regex is not UNSET:
            field_dict["regex"] = regex
        if values is not UNSET:
            field_dict["values"] = values

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        private = d.pop("private")

        required = d.pop("required")

        type_ = d.pop("type")

        default = d.pop("default", UNSET)

        def _parse_regex(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        regex = _parse_regex(d.pop("regex", UNSET))

        def _parse_values(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                values_type_0 = cast(list[str], data)

                return values_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        values = _parse_values(d.pop("values", UNSET))

        token_meta = cls(
            name=name,
            private=private,
            required=required,
            type_=type_,
            default=default,
            regex=regex,
            values=values,
        )

        token_meta.additional_properties = d
        return token_meta

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
