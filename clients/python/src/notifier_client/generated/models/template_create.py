from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.template_create_sample_variables_type_0 import TemplateCreateSampleVariablesType0
    from ..models.template_create_variables_schema_type_0 import TemplateCreateVariablesSchemaType0


T = TypeVar("T", bound="TemplateCreate")


@_attrs_define
class TemplateCreate:
    """Request body for POST /templates.

    Attributes:
        body_template (str):
        name (str):
        title_template (str):
        sample_variables (None | TemplateCreateSampleVariablesType0 | Unset):
        tags (list[str] | None | Unset):
        variables_schema (None | TemplateCreateVariablesSchemaType0 | Unset):
    """

    body_template: str
    name: str
    title_template: str
    sample_variables: None | TemplateCreateSampleVariablesType0 | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    variables_schema: None | TemplateCreateVariablesSchemaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.template_create_sample_variables_type_0 import (
            TemplateCreateSampleVariablesType0,
        )
        from ..models.template_create_variables_schema_type_0 import (
            TemplateCreateVariablesSchemaType0,
        )

        body_template = self.body_template

        name = self.name

        title_template = self.title_template

        sample_variables: dict[str, Any] | None | Unset
        if isinstance(self.sample_variables, Unset):
            sample_variables = UNSET
        elif isinstance(self.sample_variables, TemplateCreateSampleVariablesType0):
            sample_variables = self.sample_variables.to_dict()
        else:
            sample_variables = self.sample_variables

        tags: list[str] | None | Unset
        if isinstance(self.tags, Unset):
            tags = UNSET
        elif isinstance(self.tags, list):
            tags = self.tags

        else:
            tags = self.tags

        variables_schema: dict[str, Any] | None | Unset
        if isinstance(self.variables_schema, Unset):
            variables_schema = UNSET
        elif isinstance(self.variables_schema, TemplateCreateVariablesSchemaType0):
            variables_schema = self.variables_schema.to_dict()
        else:
            variables_schema = self.variables_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "body_template": body_template,
                "name": name,
                "title_template": title_template,
            }
        )
        if sample_variables is not UNSET:
            field_dict["sample_variables"] = sample_variables
        if tags is not UNSET:
            field_dict["tags"] = tags
        if variables_schema is not UNSET:
            field_dict["variables_schema"] = variables_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_create_sample_variables_type_0 import (
            TemplateCreateSampleVariablesType0,
        )
        from ..models.template_create_variables_schema_type_0 import (
            TemplateCreateVariablesSchemaType0,
        )

        d = dict(src_dict)
        body_template = d.pop("body_template")

        name = d.pop("name")

        title_template = d.pop("title_template")

        def _parse_sample_variables(
            data: object,
        ) -> None | TemplateCreateSampleVariablesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                sample_variables_type_0 = TemplateCreateSampleVariablesType0.from_dict(data)

                return sample_variables_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateCreateSampleVariablesType0 | Unset, data)

        sample_variables = _parse_sample_variables(d.pop("sample_variables", UNSET))

        def _parse_tags(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                tags_type_0 = cast(list[str], data)

                return tags_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        tags = _parse_tags(d.pop("tags", UNSET))

        def _parse_variables_schema(
            data: object,
        ) -> None | TemplateCreateVariablesSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                variables_schema_type_0 = TemplateCreateVariablesSchemaType0.from_dict(data)

                return variables_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateCreateVariablesSchemaType0 | Unset, data)

        variables_schema = _parse_variables_schema(d.pop("variables_schema", UNSET))

        template_create = cls(
            body_template=body_template,
            name=name,
            title_template=title_template,
            sample_variables=sample_variables,
            tags=tags,
            variables_schema=variables_schema,
        )

        template_create.additional_properties = d
        return template_create

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
