from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.checkin_response_previous_state import CheckinResponsePreviousState
from ..models.checkin_response_state import CheckinResponseState

if TYPE_CHECKING:
    from ..models.dispatch_out import DispatchOut


T = TypeVar("T", bound="CheckinResponse")


@_attrs_define
class CheckinResponse:
    """Response body for POST /monitors/{id}/checkin.

    Attributes:
        dispatches (list[DispatchOut]):
        last_checkin_at (datetime.datetime):
        monitor_id (str):
        next_deadline_at (datetime.datetime):
        previous_state (CheckinResponsePreviousState):
        state (CheckinResponseState):
    """

    dispatches: list[DispatchOut]
    last_checkin_at: datetime.datetime
    monitor_id: str
    next_deadline_at: datetime.datetime
    previous_state: CheckinResponsePreviousState
    state: CheckinResponseState
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dispatches = []
        for dispatches_item_data in self.dispatches:
            dispatches_item = dispatches_item_data.to_dict()
            dispatches.append(dispatches_item)

        last_checkin_at = self.last_checkin_at.isoformat()

        monitor_id = self.monitor_id

        next_deadline_at = self.next_deadline_at.isoformat()

        previous_state = self.previous_state.value

        state = self.state.value

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dispatches": dispatches,
                "last_checkin_at": last_checkin_at,
                "monitor_id": monitor_id,
                "next_deadline_at": next_deadline_at,
                "previous_state": previous_state,
                "state": state,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dispatch_out import DispatchOut  # noqa: PLC0415

        d = dict(src_dict)
        dispatches = []
        _dispatches = d.pop("dispatches")
        for dispatches_item_data in _dispatches:
            dispatches_item = DispatchOut.from_dict(dispatches_item_data)

            dispatches.append(dispatches_item)

        last_checkin_at = datetime.datetime.fromisoformat(d.pop("last_checkin_at"))

        monitor_id = d.pop("monitor_id")

        next_deadline_at = datetime.datetime.fromisoformat(d.pop("next_deadline_at"))

        previous_state = CheckinResponsePreviousState(d.pop("previous_state"))

        state = CheckinResponseState(d.pop("state"))

        checkin_response = cls(
            dispatches=dispatches,
            last_checkin_at=last_checkin_at,
            monitor_id=monitor_id,
            next_deadline_at=next_deadline_at,
            previous_state=previous_state,
            state=state,
        )

        checkin_response.additional_properties = d
        return checkin_response

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
