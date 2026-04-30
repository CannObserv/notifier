from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.template_preview_request_variables_type_0 import (
        TemplatePreviewRequestVariablesType0,
    )


T = TypeVar("T", bound="TemplatePreviewRequest")


@_attrs_define
class TemplatePreviewRequest:
    """Request body for POST /templates/{id}/preview.

    If ``variables`` is omitted, the template's stored ``sample_variables``
    are used (handy for "preview as it would look out of the box").

        Attributes:
            variables (None | TemplatePreviewRequestVariablesType0 | Unset):
    """

    variables: None | TemplatePreviewRequestVariablesType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.template_preview_request_variables_type_0 import (
            TemplatePreviewRequestVariablesType0,
        )

        variables: dict[str, Any] | None | Unset
        if isinstance(self.variables, Unset):
            variables = UNSET
        elif isinstance(self.variables, TemplatePreviewRequestVariablesType0):
            variables = self.variables.to_dict()
        else:
            variables = self.variables

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if variables is not UNSET:
            field_dict["variables"] = variables

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_preview_request_variables_type_0 import (
            TemplatePreviewRequestVariablesType0,
        )

        d = dict(src_dict)

        def _parse_variables(data: object) -> None | TemplatePreviewRequestVariablesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                variables_type_0 = TemplatePreviewRequestVariablesType0.from_dict(data)

                return variables_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplatePreviewRequestVariablesType0 | Unset, data)

        variables = _parse_variables(d.pop("variables", UNSET))

        template_preview_request = cls(
            variables=variables,
        )

        template_preview_request.additional_properties = d
        return template_preview_request

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
