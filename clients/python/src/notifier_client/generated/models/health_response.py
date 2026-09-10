from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="HealthResponse")


@_attrs_define
class HealthResponse:
    """Liveness payload, including which deployment answered.

    ``build`` cannot distinguish the two endpoints: both units serve one
    working tree, so the SHA agreeing is correct and will keep agreeing
    (#58). ``environment`` is the field to assert on, and it carries the same
    vocabulary as an API key's own marking — so a consumer sees the mismatch
    here before the 403 in ``require_api_key`` tells it the same thing.

        Attributes:
            build (str):
            database (str):
            environment (str):
            status (str):
    """

    build: str
    database: str
    environment: str
    status: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        build = self.build

        database = self.database

        environment = self.environment

        status = self.status

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "build": build,
                "database": database,
                "environment": environment,
                "status": status,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        build = d.pop("build")

        database = d.pop("database")

        environment = d.pop("environment")

        status = d.pop("status")

        health_response = cls(
            build=build,
            database=database,
            environment=environment,
            status=status,
        )

        health_response.additional_properties = d
        return health_response

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
