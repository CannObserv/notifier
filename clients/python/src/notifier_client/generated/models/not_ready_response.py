from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="NotReadyResponse")


@_attrs_define
class NotReadyResponse:
    """The 503 payload — no connection, so nothing to name.

    A separate model rather than a loosened ``ReadyResponse``: the 503 says
    only that the database could not be reached, and the shape it has carried
    since before the probes learned to name a database is the honest one.

        Attributes:
            db (bool):
            status (str):
    """

    db: bool
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        db = self.db

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "db": db,
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        db = d.pop("db")

        status = d.pop("status")

        not_ready_response = cls(
            db=db,
            status=status,
        )

        not_ready_response.additional_properties = d
        return not_ready_response

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
