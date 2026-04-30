"""Apprise plugin catalog API endpoints."""

from fastapi import APIRouter, HTTPException

from src.api.schemas.apprise_plugin import (
    AssembleRequest,
    AssembleResponse,
    PluginDetail,
    PluginListItem,
    PluginVariant,
    TokenMeta,
)
from src.core.notifications.apprise_builder import (
    assemble_url,
    get_plugin_detail,
    list_plugins,
)

router = APIRouter(prefix="/apprise", tags=["apprise"])


@router.get("/plugins", response_model=list[PluginListItem])
async def list_apprise_plugins() -> list[dict]:
    """List all available Apprise notification plugins."""
    return list_plugins()


@router.get("/plugins/{schema}", response_model=PluginDetail)
async def get_apprise_plugin(schema: str) -> PluginDetail:
    """Return token definitions and variant info for an Apprise plugin."""
    detail = get_plugin_detail(schema)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown Apprise plugin: {schema!r}")
    return PluginDetail(
        plugin_schema=detail["plugin_schema"],
        service_name=detail["service_name"],
        setup_url=detail.get("setup_url"),
        service_url=detail.get("service_url"),
        tokens={k: TokenMeta(**v) for k, v in detail["tokens"].items()},
        variants=[PluginVariant(**v) for v in detail["variants"]],
    )


@router.post("/plugins/{schema}/assemble", response_model=AssembleResponse)
async def assemble_apprise_url(schema: str, body: AssembleRequest) -> AssembleResponse:
    """Assemble a candidate Apprise URL from a token bag without persisting it."""
    if get_plugin_detail(schema) is None:
        raise HTTPException(status_code=404, detail=f"Unknown Apprise plugin: {schema!r}")
    try:
        url = assemble_url(schema, body.tokens, variant_index=body.variant_index)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssembleResponse(apprise_url=url)
