"""Pydantic response schemas for the Apprise plugin catalog endpoints."""

from typing import Any

from pydantic import BaseModel


class TokenMeta(BaseModel):
    """Metadata for a single Apprise plugin token."""

    name: str
    type: str
    required: bool
    private: bool
    default: Any = None
    values: list[str] | None = None
    regex: str | None = None


class PluginVariant(BaseModel):
    """A template variant for plugins with divergent required-token sets."""

    label: str
    required_token_names: list[str]


class PluginListItem(BaseModel):
    """Summary item for the plugin list endpoint."""

    plugin_schema: str
    service_name: str
    setup_url: str | None = None
    service_url: str | None = None
    category: str | None = None


class PluginDetail(BaseModel):
    """Full plugin detail including token definitions and variants."""

    plugin_schema: str
    service_name: str
    setup_url: str | None = None
    service_url: str | None = None
    tokens: dict[str, TokenMeta]
    variants: list[PluginVariant]


class AssembleRequest(BaseModel):
    """POST /apprise/plugins/{schema}/assemble — token bag + variant index."""

    tokens: dict[str, str]
    variant_index: int | None = None


class AssembleResponse(BaseModel):
    """Returned by /assemble: the validated Apprise URL string."""

    apprise_url: str
