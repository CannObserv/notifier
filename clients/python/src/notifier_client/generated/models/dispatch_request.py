from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.dispatch_request_metadata import DispatchRequestMetadata
    from ..models.dispatch_request_variables import DispatchRequestVariables


T = TypeVar("T", bound="DispatchRequest")


@_attrs_define
class DispatchRequest:
    """Request body for POST /dispatch.

    Either ``template_id`` *or* both ``title_template`` and ``body_template``
    must be supplied. Inline templates take precedence over a stored template
    if both are provided (useful for stage rollouts of new wording).

        Attributes:
            channel_ids (list[str]):
            body_template (None | str | Unset):
            idempotency_key (None | str | Unset):
            metadata (DispatchRequestMetadata | Unset):
            template_id (None | str | Unset):
            title_template (None | str | Unset):
            variables (DispatchRequestVariables | Unset):
    """

    channel_ids: list[str]
    body_template: None | str | Unset = UNSET
    idempotency_key: None | str | Unset = UNSET
    metadata: DispatchRequestMetadata | Unset = UNSET
    template_id: None | str | Unset = UNSET
    title_template: None | str | Unset = UNSET
    variables: DispatchRequestVariables | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        channel_ids = self.channel_ids

        body_template: None | str | Unset
        if isinstance(self.body_template, Unset):
            body_template = UNSET
        else:
            body_template = self.body_template

        idempotency_key: None | str | Unset
        if isinstance(self.idempotency_key, Unset):
            idempotency_key = UNSET
        else:
            idempotency_key = self.idempotency_key

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        template_id: None | str | Unset
        if isinstance(self.template_id, Unset):
            template_id = UNSET
        else:
            template_id = self.template_id

        title_template: None | str | Unset
        if isinstance(self.title_template, Unset):
            title_template = UNSET
        else:
            title_template = self.title_template

        variables: dict[str, Any] | Unset = UNSET
        if not isinstance(self.variables, Unset):
            variables = self.variables.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "channel_ids": channel_ids,
            }
        )
        if body_template is not UNSET:
            field_dict["body_template"] = body_template
        if idempotency_key is not UNSET:
            field_dict["idempotency_key"] = idempotency_key
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if template_id is not UNSET:
            field_dict["template_id"] = template_id
        if title_template is not UNSET:
            field_dict["title_template"] = title_template
        if variables is not UNSET:
            field_dict["variables"] = variables

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dispatch_request_metadata import DispatchRequestMetadata
        from ..models.dispatch_request_variables import DispatchRequestVariables

        d = dict(src_dict)
        channel_ids = cast(list[str], d.pop("channel_ids"))

        def _parse_body_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        body_template = _parse_body_template(d.pop("body_template", UNSET))

        def _parse_idempotency_key(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        idempotency_key = _parse_idempotency_key(d.pop("idempotency_key", UNSET))

        _metadata = d.pop("metadata", UNSET)
        metadata: DispatchRequestMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = DispatchRequestMetadata.from_dict(_metadata)

        def _parse_template_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        template_id = _parse_template_id(d.pop("template_id", UNSET))

        def _parse_title_template(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title_template = _parse_title_template(d.pop("title_template", UNSET))

        _variables = d.pop("variables", UNSET)
        variables: DispatchRequestVariables | Unset
        if isinstance(_variables, Unset):
            variables = UNSET
        else:
            variables = DispatchRequestVariables.from_dict(_variables)

        dispatch_request = cls(
            channel_ids=channel_ids,
            body_template=body_template,
            idempotency_key=idempotency_key,
            metadata=metadata,
            template_id=template_id,
            title_template=title_template,
            variables=variables,
        )

        dispatch_request.additional_properties = d
        return dispatch_request

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
