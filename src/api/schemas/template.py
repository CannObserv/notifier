"""Pydantic schemas for the template endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    """Request body for POST /templates."""

    name: str = Field(min_length=1, max_length=200)
    title_template: str
    body_template: str
    variables_schema: dict[str, Any] | None = None
    sample_variables: dict[str, Any] | None = None
    tags: list[str] | None = None


class TemplateUpdate(BaseModel):
    """Request body for PATCH /templates/{id} — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    title_template: str | None = None
    body_template: str | None = None
    variables_schema: dict[str, Any] | None = None
    sample_variables: dict[str, Any] | None = None
    tags: list[str] | None = None


class TemplateOut(BaseModel):
    """Response body for any template endpoint."""

    id: str
    tenant_id: str
    name: str
    title_template: str
    body_template: str
    variables_schema: dict[str, Any] | None = None
    sample_variables: dict[str, Any] | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class TemplatePreviewRequest(BaseModel):
    """Request body for POST /templates/{id}/preview.

    If ``variables`` is omitted, the template's stored ``sample_variables``
    are used (handy for "preview as it would look out of the box").
    """

    variables: dict[str, Any] | None = None


class TemplatePreviewResponse(BaseModel):
    """Response body for POST /templates/{id}/preview."""

    title: str | None = None
    body: str | None = None
    error: str | None = None
    error_section: str | None = None  # "title" | "body" | "variables"
