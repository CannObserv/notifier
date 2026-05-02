"""Pydantic schemas for the dispatch endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.api.schemas.types import ULIDStr


class DispatchRequest(BaseModel):
    """Request body for POST /dispatch.

    Either ``template_id`` *or* both ``title_template`` and ``body_template``
    must be supplied. Inline templates take precedence over a stored template
    if both are provided (useful for stage rollouts of new wording).
    """

    template_id: ULIDStr | None = None
    title_template: str | None = None
    body_template: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    channel_ids: list[ULIDStr] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_template_source(self) -> "DispatchRequest":
        if self.template_id is None and (
            self.title_template is None or self.body_template is None
        ):
            raise ValueError(
                "either template_id or both title_template+body_template are required"
            )
        return self


class DispatchAttemptOut(BaseModel):
    """Response body fragment representing one channel attempt."""

    channel_id: str
    # Literal instead of DispatchStatus enum: Pydantic emits an inline enum array
    # in the OpenAPI spec, which openapi-python-client codegen maps to a typed enum
    # field on the generated model. Using the StrEnum directly would emit a $ref
    # schema, producing a differently-named generated class and a different wire shape.
    # tests/core/test_dispatch_constants.py cross-checks these values stay in sync.
    status: Literal["succeeded", "failed"]
    reason: str
    attempt: int
    started_at: datetime
    finished_at: datetime | None = None


class DispatchOut(BaseModel):
    """Response body for POST /dispatch and GET /dispatch/{id}."""

    id: str
    tenant_id: str
    template_id: str | None
    idempotency_key: str | None
    rendered_title: str
    rendered_body: str
    # See DispatchAttemptOut.status comment above for why Literal is used here.
    status: Literal["succeeded", "partial", "failed"]
    metadata: dict[str, Any]
    created_at: datetime
    attempts: list[DispatchAttemptOut]
