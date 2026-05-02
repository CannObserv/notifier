"""Template CRUD + per-template preview endpoint."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_api_key
from src.api.schemas.template import (
    TemplateCreate,
    TemplateOut,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateUpdate,
)
from src.api.schemas.types import ULIDStr
from src.core.models.template import Template
from src.core.notifications.render import TemplateRenderError, render_template
from src.core.notifications.validate import VariablesValidationError, validate_variables

router = APIRouter(prefix="/templates", tags=["templates"])


def _to_out(t: Template) -> TemplateOut:
    return TemplateOut(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        name=t.name,
        title_template=t.title_template,
        body_template=t.body_template,
        variables_schema=t.variables_schema,
        sample_variables=t.sample_variables,
        tags=t.tags,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def _load_owned(
    session: AsyncSession, template_id: str, tenant_id: str
) -> Template:
    result = await session.execute(
        select(Template).where(Template.id == template_id, Template.tenant_id == tenant_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> list[TemplateOut]:
    """List all templates owned by the calling tenant."""
    result = await session.execute(
        select(Template).where(Template.tenant_id == tenant_id).order_by(Template.created_at)
    )
    return [_to_out(t) for t in result.scalars().all()]


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> TemplateOut:
    """Create a new template for the calling tenant."""
    template = Template(
        tenant_id=tenant_id,
        name=body.name,
        title_template=body.title_template,
        body_template=body.body_template,
        variables_schema=body.variables_schema,
        sample_variables=body.sample_variables,
        tags=body.tags,
    )
    session.add(template)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Template name already exists") from exc
    await session.refresh(template)
    return _to_out(template)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> TemplateOut:
    """Fetch a single template by ID."""
    return _to_out(await _load_owned(session, template_id, tenant_id))


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: ULIDStr,
    body: TemplateUpdate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> TemplateOut:
    """Partially update a template; only supplied fields are changed."""
    template = await _load_owned(session, template_id, tenant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Template name already exists") from exc
    await session.refresh(template)
    return _to_out(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a template. Existing dispatch logs retain their template_id as null."""
    template = await _load_owned(session, template_id, tenant_id)
    await session.delete(template)
    await session.commit()


@router.post("/{template_id}/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    template_id: ULIDStr,
    body: TemplatePreviewRequest,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> TemplatePreviewResponse:
    """Render a template against supplied or sample variables; never dispatches."""
    template = await _load_owned(session, template_id, tenant_id)
    variables: dict[str, Any] = body.variables or template.sample_variables or {}

    try:
        validate_variables(variables, template.variables_schema)
    except VariablesValidationError as exc:
        return TemplatePreviewResponse(error=str(exc), error_section="variables")

    try:
        title = render_template(template.title_template, variables)
    except TemplateRenderError as exc:
        return TemplatePreviewResponse(error=str(exc), error_section="title")
    try:
        body_str = render_template(template.body_template, variables)
    except TemplateRenderError as exc:
        return TemplatePreviewResponse(error=str(exc), error_section="body")

    return TemplatePreviewResponse(title=title, body=body_str)
