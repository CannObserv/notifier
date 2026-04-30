"""Pydantic schemas for the channel endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    """Request body for POST /channels."""

    name: str = Field(min_length=1, max_length=200)
    apprise_url: str  # plaintext on the wire; encrypted at rest
    channel_hint: str | None = None


class ChannelUpdate(BaseModel):
    """Request body for PATCH /channels/{id} — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    apprise_url: str | None = None
    channel_hint: str | None = None


class ChannelOut(BaseModel):
    """Response body for any channel endpoint.

    The Apprise URL is never returned — only its masked prefix.
    """

    id: str
    tenant_id: str
    name: str
    apprise_url_masked: str
    channel_hint: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelTestResponse(BaseModel):
    """Response body for POST /channels/{id}/test."""

    success: bool
    reason: str
