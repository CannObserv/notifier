from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..models.dispatch_out_status import DispatchOutStatus

if TYPE_CHECKING:
    from ..models.dispatch_attempt_out import DispatchAttemptOut
    from ..models.dispatch_out_metadata import DispatchOutMetadata


T = TypeVar("T", bound="DispatchOut")


@_attrs_define
class DispatchOut:
    """Response body for POST /dispatch and GET /dispatch/{id}.

    Attributes:
        attempts (list[DispatchAttemptOut]):
        created_at (datetime.datetime):
        id (str):
        idempotency_key (None | str):
        metadata (DispatchOutMetadata):
        rendered_body (str):
        rendered_title (str):
        status (DispatchOutStatus):
        template_id (None | str):
        tenant_id (str):
    """

    attempts: list[DispatchAttemptOut]
    created_at: datetime.datetime
    id: str
    idempotency_key: None | str
    metadata: DispatchOutMetadata
    rendered_body: str
    rendered_title: str
    status: DispatchOutStatus
    template_id: None | str
    tenant_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        attempts = []
        for attempts_item_data in self.attempts:
            attempts_item = attempts_item_data.to_dict()
            attempts.append(attempts_item)

        created_at = self.created_at.isoformat()

        id = self.id

        idempotency_key: None | str
        idempotency_key = self.idempotency_key

        metadata = self.metadata.to_dict()

        rendered_body = self.rendered_body

        rendered_title = self.rendered_title

        status = self.status.value

        template_id: None | str
        template_id = self.template_id

        tenant_id = self.tenant_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "attempts": attempts,
                "created_at": created_at,
                "id": id,
                "idempotency_key": idempotency_key,
                "metadata": metadata,
                "rendered_body": rendered_body,
                "rendered_title": rendered_title,
                "status": status,
                "template_id": template_id,
                "tenant_id": tenant_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.dispatch_attempt_out import DispatchAttemptOut
        from ..models.dispatch_out_metadata import DispatchOutMetadata

        d = dict(src_dict)
        attempts = []
        _attempts = d.pop("attempts")
        for attempts_item_data in _attempts:
            attempts_item = DispatchAttemptOut.from_dict(attempts_item_data)

            attempts.append(attempts_item)

        created_at = isoparse(d.pop("created_at"))

        id = d.pop("id")

        def _parse_idempotency_key(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        idempotency_key = _parse_idempotency_key(d.pop("idempotency_key"))

        metadata = DispatchOutMetadata.from_dict(d.pop("metadata"))

        rendered_body = d.pop("rendered_body")

        rendered_title = d.pop("rendered_title")

        status = DispatchOutStatus(d.pop("status"))

        def _parse_template_id(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        template_id = _parse_template_id(d.pop("template_id"))

        tenant_id = d.pop("tenant_id")

        dispatch_out = cls(
            attempts=attempts,
            created_at=created_at,
            id=id,
            idempotency_key=idempotency_key,
            metadata=metadata,
            rendered_body=rendered_body,
            rendered_title=rendered_title,
            status=status,
            template_id=template_id,
            tenant_id=tenant_id,
        )

        dispatch_out.additional_properties = d
        return dispatch_out

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
