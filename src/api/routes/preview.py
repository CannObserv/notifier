"""Stateless template preview endpoint — no persistence."""

from fastapi import APIRouter, Depends

from src.api.deps import require_api_key
from src.api.schemas.preview import PreviewRequest, PreviewResponse
from src.core.notifications.render import TemplateRenderError, render_template
from src.core.notifications.validate import VariablesValidationError, validate_variables

router = APIRouter(prefix="/preview", tags=["preview"])


@router.post("", response_model=PreviewResponse)
async def preview(
    body: PreviewRequest,
    _tenant_id: str = Depends(require_api_key),
) -> PreviewResponse:
    """Render inline templates with supplied variables; returns errors per section."""
    try:
        validate_variables(body.variables, body.variables_schema)
    except VariablesValidationError as exc:
        return PreviewResponse(error=str(exc), error_section="variables")

    try:
        title = render_template(body.title_template, body.variables)
    except TemplateRenderError as exc:
        return PreviewResponse(error=str(exc), error_section="title")

    try:
        body_str = render_template(body.body_template, body.variables)
    except TemplateRenderError as exc:
        return PreviewResponse(error=str(exc), error_section="body")

    return PreviewResponse(title=title, body=body_str)
