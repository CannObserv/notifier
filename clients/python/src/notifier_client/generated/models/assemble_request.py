from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.assemble_request_tokens import AssembleRequestTokens


T = TypeVar("T", bound="AssembleRequest")


@_attrs_define
class AssembleRequest:
    """POST /apprise/plugins/{schema}/assemble — token bag + variant index.

    Attributes:
        tokens (AssembleRequestTokens):
        variant_index (int | None | Unset):
    """

    tokens: AssembleRequestTokens
    variant_index: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        tokens = self.tokens.to_dict()

        variant_index: int | None | Unset
        if isinstance(self.variant_index, Unset):
            variant_index = UNSET
        else:
            variant_index = self.variant_index

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "tokens": tokens,
            }
        )
        if variant_index is not UNSET:
            field_dict["variant_index"] = variant_index

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.assemble_request_tokens import AssembleRequestTokens

        d = dict(src_dict)
        tokens = AssembleRequestTokens.from_dict(d.pop("tokens"))

        def _parse_variant_index(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        variant_index = _parse_variant_index(d.pop("variant_index", UNSET))

        assemble_request = cls(
            tokens=tokens,
            variant_index=variant_index,
        )

        assemble_request.additional_properties = d
        return assemble_request

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
