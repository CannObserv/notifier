from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.preview_request_variables import PreviewRequestVariables
    from ..models.preview_request_variables_schema_type_0 import PreviewRequestVariablesSchemaType0


T = TypeVar("T", bound="PreviewRequest")


@_attrs_define
class PreviewRequest:
    """Request body for POST /preview — inline templates + variables.

    Attributes:
        body_template (str):
        title_template (str):
        variables (PreviewRequestVariables):
        variables_schema (None | PreviewRequestVariablesSchemaType0 | Unset):
    """

    body_template: str
    title_template: str
    variables: PreviewRequestVariables
    variables_schema: None | PreviewRequestVariablesSchemaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.preview_request_variables_schema_type_0 import (
            PreviewRequestVariablesSchemaType0,
        )

        body_template = self.body_template

        title_template = self.title_template

        variables = self.variables.to_dict()

        variables_schema: dict[str, Any] | None | Unset
        if isinstance(self.variables_schema, Unset):
            variables_schema = UNSET
        elif isinstance(self.variables_schema, PreviewRequestVariablesSchemaType0):
            variables_schema = self.variables_schema.to_dict()
        else:
            variables_schema = self.variables_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "body_template": body_template,
                "title_template": title_template,
                "variables": variables,
            }
        )
        if variables_schema is not UNSET:
            field_dict["variables_schema"] = variables_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.preview_request_variables import PreviewRequestVariables
        from ..models.preview_request_variables_schema_type_0 import (
            PreviewRequestVariablesSchemaType0,
        )

        d = dict(src_dict)
        body_template = d.pop("body_template")

        title_template = d.pop("title_template")

        variables = PreviewRequestVariables.from_dict(d.pop("variables"))

        def _parse_variables_schema(
            data: object,
        ) -> None | PreviewRequestVariablesSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                variables_schema_type_0 = PreviewRequestVariablesSchemaType0.from_dict(data)

                return variables_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | PreviewRequestVariablesSchemaType0 | Unset, data)

        variables_schema = _parse_variables_schema(d.pop("variables_schema", UNSET))

        preview_request = cls(
            body_template=body_template,
            title_template=title_template,
            variables=variables,
            variables_schema=variables_schema,
        )

        preview_request.additional_properties = d
        return preview_request

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
