"""Pydantic schemas for the stateless preview endpoint."""

from typing import Any

from pydantic import BaseModel


class PreviewRequest(BaseModel):
    """Request body for POST /preview — inline templates + variables."""

    title_template: str
    body_template: str
    variables: dict[str, Any]
    variables_schema: dict[str, Any] | None = None


class PreviewResponse(BaseModel):
    """Response body for POST /preview.

    On success, ``title`` and ``body`` are populated and ``error`` is ``None``.
    On error, ``error`` carries the message and ``error_section`` indicates
    which input failed: ``"title"``, ``"body"``, or ``"variables"``.
    """

    title: str | None = None
    body: str | None = None
    error: str | None = None
    error_section: str | None = None
