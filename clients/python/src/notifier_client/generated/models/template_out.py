from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.template_out_sample_variables_type_0 import TemplateOutSampleVariablesType0
    from ..models.template_out_variables_schema_type_0 import TemplateOutVariablesSchemaType0


T = TypeVar("T", bound="TemplateOut")


@_attrs_define
class TemplateOut:
    """Response body for any template endpoint.

    Attributes:
        body_template (str):
        created_at (datetime.datetime):
        id (str):
        name (str):
        tenant_id (str):
        title_template (str):
        updated_at (datetime.datetime):
        sample_variables (None | TemplateOutSampleVariablesType0 | Unset):
        tags (list[str] | None | Unset):
        variables_schema (None | TemplateOutVariablesSchemaType0 | Unset):
    """

    body_template: str
    created_at: datetime.datetime
    id: str
    name: str
    tenant_id: str
    title_template: str
    updated_at: datetime.datetime
    sample_variables: None | TemplateOutSampleVariablesType0 | Unset = UNSET
    tags: list[str] | None | Unset = UNSET
    variables_schema: None | TemplateOutVariablesSchemaType0 | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.template_out_sample_variables_type_0 import TemplateOutSampleVariablesType0
        from ..models.template_out_variables_schema_type_0 import TemplateOutVariablesSchemaType0

        body_template = self.body_template

        created_at = self.created_at.isoformat()

        id = self.id

        name = self.name

        tenant_id = self.tenant_id

        title_template = self.title_template

        updated_at = self.updated_at.isoformat()

        sample_variables: dict[str, Any] | None | Unset
        if isinstance(self.sample_variables, Unset):
            sample_variables = UNSET
        elif isinstance(self.sample_variables, TemplateOutSampleVariablesType0):
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
        elif isinstance(self.variables_schema, TemplateOutVariablesSchemaType0):
            variables_schema = self.variables_schema.to_dict()
        else:
            variables_schema = self.variables_schema

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "body_template": body_template,
                "created_at": created_at,
                "id": id,
                "name": name,
                "tenant_id": tenant_id,
                "title_template": title_template,
                "updated_at": updated_at,
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
        from ..models.template_out_sample_variables_type_0 import TemplateOutSampleVariablesType0
        from ..models.template_out_variables_schema_type_0 import TemplateOutVariablesSchemaType0

        d = dict(src_dict)
        body_template = d.pop("body_template")

        created_at = isoparse(d.pop("created_at"))

        id = d.pop("id")

        name = d.pop("name")

        tenant_id = d.pop("tenant_id")

        title_template = d.pop("title_template")

        updated_at = isoparse(d.pop("updated_at"))

        def _parse_sample_variables(data: object) -> None | TemplateOutSampleVariablesType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                sample_variables_type_0 = TemplateOutSampleVariablesType0.from_dict(data)

                return sample_variables_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateOutSampleVariablesType0 | Unset, data)

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

        def _parse_variables_schema(data: object) -> None | TemplateOutVariablesSchemaType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                variables_schema_type_0 = TemplateOutVariablesSchemaType0.from_dict(data)

                return variables_schema_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | TemplateOutVariablesSchemaType0 | Unset, data)

        variables_schema = _parse_variables_schema(d.pop("variables_schema", UNSET))

        template_out = cls(
            body_template=body_template,
            created_at=created_at,
            id=id,
            name=name,
            tenant_id=tenant_id,
            title_template=title_template,
            updated_at=updated_at,
            sample_variables=sample_variables,
            tags=tags,
            variables_schema=variables_schema,
        )

        template_out.additional_properties = d
        return template_out

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
