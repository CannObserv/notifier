from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="DispatchAttemptOut")


@_attrs_define
class DispatchAttemptOut:
    """Response body fragment representing one channel attempt.

    Attributes:
        attempt (int):
        channel_id (str):
        reason (str):
        started_at (datetime.datetime):
        status (str):
        finished_at (datetime.datetime | None | Unset):
    """

    attempt: int
    channel_id: str
    reason: str
    started_at: datetime.datetime
    status: str
    finished_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attempt = self.attempt

        channel_id = self.channel_id

        reason = self.reason

        started_at = self.started_at.isoformat()

        status = self.status

        finished_at: None | str | Unset
        if isinstance(self.finished_at, Unset):
            finished_at = UNSET
        elif isinstance(self.finished_at, datetime.datetime):
            finished_at = self.finished_at.isoformat()
        else:
            finished_at = self.finished_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attempt": attempt,
                "channel_id": channel_id,
                "reason": reason,
                "started_at": started_at,
                "status": status,
            }
        )
        if finished_at is not UNSET:
            field_dict["finished_at"] = finished_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        attempt = d.pop("attempt")

        channel_id = d.pop("channel_id")

        reason = d.pop("reason")

        started_at = isoparse(d.pop("started_at"))

        status = d.pop("status")

        def _parse_finished_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                finished_at_type_0 = isoparse(data)

                return finished_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        finished_at = _parse_finished_at(d.pop("finished_at", UNSET))

        dispatch_attempt_out = cls(
            attempt=attempt,
            channel_id=channel_id,
            reason=reason,
            started_at=started_at,
            status=status,
            finished_at=finished_at,
        )

        dispatch_attempt_out.additional_properties = d
        return dispatch_attempt_out

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
