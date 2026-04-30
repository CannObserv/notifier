from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.template_update_sample_variables_type_0 import TemplateUpdateSampleVariablesType0
    from ..models.template_update_variables_schema_type_0 import TemplateUpdateVariablesSchemaType0


T = TypeVar("T", bound="TemplateUpdate")


@_attrs_define
class TemplateUpdate:
    """Request body for PATCH /templates/{id} — all fields optional.

    Attributes:
        body_template (None | str | Unset):
        name (None | str | Unset):
        sample_variables (None | TemplateUpdateSampleVariablesType0 | Unset):
        tags (list[str] | None | Unset):
        title_template (None | str | Unset):
        variables_schema (None | TemplateUpdateVariablesSchemaType0 | Unset):
    """

    body_template: None | str | Unset = UNSET
    name: None | str | Unset = UNSET
    sample_variables: None | TemplateUpdateSampleVariablesType0 | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    title_template: None | str | Unset = UNSET
    variables_schema: None | TemplateUpdateVariablesSchemaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.template_update_sample_variables_type_0 import (
            TemplateUpdateSampleVariablesType0,
        )
        from ..models.template_update_variables_schema_type_0 import (
            TemplateUpdateVariablesSchemaType0,
        )

        body_template: None | str | Unset
        if isinstance(self.body_template, Unset):
            body_template = UNSET
        else:
            body_template = self.body_template

        name: None | str | Unset
        if isinstance(self.name, Unset):
            name = UNSET
        else:
            name = self.name

        sample_variables: dict[str, Any] | None | Unset
        if isinstance(self.sample_variables, Unset):
            sample_variables = UNSET
        elif isinstance(self.sample_variables, TemplateUpdateSampleVariablesType0):
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

        title_template: None | str | Unset
        if isinstance(self.title_template, Unset):
            title_template = UNSET
        else:
            title_template = self.title_template

        variables_schema: dict[str, Any] | None | Unset
        if isinstance(self.variables_schema, Unset):
            variables_schema = UNSET
        elif isinstance(self.variables_schema, TemplateUpdateVariablesSchemaType0):
            variables_schema = self.variables_schema.to_dict()
        else:
            variables_schema = self.variables_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if body_template is not UNSET:
            field_dict["body_template"] = body_template
        if name is not UNSET:
            field_dict["name"] = name
        if sample_variables is not UNSET:
            field_dict["sample_variables"] = sample_variables
        if tags is not UNSET:
            field_dict["tags"] = tags
        if title_template is not UNSET:
            field_dict["title_template"] = title_template
        if variables_schema is not UNSET:
            field_dict["variables_schema"] = variables_schema

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.template_update_sample_variables_type_0 import (
            TemplateUpdateSampleVariablesType0,
        )
        from ..models.template_update_variables_schema_type_0 import (
            TemplateUpdateVariablesSchemaType0,
        )

        d = dict(src_dict)

        def _parse_body_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        body_template = _parse_body_template(d.pop("body_template", UNSET))

        def _parse_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        name = _parse_name(d.pop("name", UNSET))

        def _parse_sample_variables(
            data: object,
        ) -> None | TemplateUpdateSampleVariablesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                sample_variables_type_0 = TemplateUpdateSampleVariablesType0.from_dict(data)

                return sample_variables_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateUpdateSampleVariablesType0 | Unset, data)

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

        def _parse_title_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title_template = _parse_title_template(d.pop("title_template", UNSET))

        def _parse_variables_schema(
            data: object,
        ) -> None | TemplateUpdateVariablesSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                variables_schema_type_0 = TemplateUpdateVariablesSchemaType0.from_dict(data)

                return variables_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateUpdateVariablesSchemaType0 | Unset, data)

        variables_schema = _parse_variables_schema(d.pop("variables_schema", UNSET))

        template_update = cls(
            body_template=body_template,
            name=name,
            sample_variables=sample_variables,
            tags=tags,
            title_template=title_template,
            variables_schema=variables_schema,
        )

        template_update.additional_properties = d
        return template_update

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
