from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.checkin_request_status import CheckinRequestStatus
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.checkin_request_metadata import CheckinRequestMetadata
    from ..models.checkin_request_variables import CheckinRequestVariables


T = TypeVar("T", bound="CheckinRequest")


@_attrs_define
class CheckinRequest:
    """Request body for POST /monitors/{id}/checkin.

    Send one **every tick, regardless of findings** — the arrival is the
    signal. ``status`` is the consumer's own judgement about the contents:
    ``alert`` renders and dispatches the monitor's template, ``ok`` records
    the check-in and sends nothing.

        Attributes:
            metadata (CheckinRequestMetadata | Unset):
            status (CheckinRequestStatus | Unset):  Default: CheckinRequestStatus.OK.
            variables (CheckinRequestVariables | Unset):
    """

    metadata: CheckinRequestMetadata | Unset = UNSET
    status: CheckinRequestStatus | Unset = CheckinRequestStatus.OK
    variables: CheckinRequestVariables | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        status: str | Unset = UNSET
        if not isinstance(self.status, Unset):
            status = self.status.value

        variables: dict[str, Any] | Unset = UNSET
        if not isinstance(self.variables, Unset):
            variables = self.variables.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if status is not UNSET:
            field_dict["status"] = status
        if variables is not UNSET:
            field_dict["variables"] = variables

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.checkin_request_metadata import CheckinRequestMetadata  # noqa: PLC0415
        from ..models.checkin_request_variables import CheckinRequestVariables  # noqa: PLC0415

        d = dict(src_dict)
        _metadata = d.pop("metadata", UNSET)
        metadata: CheckinRequestMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = CheckinRequestMetadata.from_dict(_metadata)

        _status = d.pop("status", UNSET)
        status: CheckinRequestStatus | Unset
        if isinstance(_status, Unset):
            status = UNSET
        else:
            status = CheckinRequestStatus(_status)

        _variables = d.pop("variables", UNSET)
        variables: CheckinRequestVariables | Unset
        if isinstance(_variables, Unset):
            variables = UNSET
        else:
            variables = CheckinRequestVariables.from_dict(_variables)

        checkin_request = cls(
            metadata=metadata,
            status=status,
            variables=variables,
        )

        checkin_request.additional_properties = d
        return checkin_request

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
