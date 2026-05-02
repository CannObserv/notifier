"""Dispatch endpoint — the core consumer-facing surface.

Renders title + body, validates variables against the template schema (if a
template is referenced), inserts a Dispatch row, then fans out to each channel
synchronously and records DispatchAttempt rows. Returns the dispatch_id and
per-channel results.

Idempotency: if ``idempotency_key`` is supplied and a Dispatch already exists
for the same (tenant_id, idempotency_key), the existing record is returned
without re-rendering or re-dispatching. This makes consumer retries safe.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_db_session, require_api_key
from src.api.schemas.dispatch import (
    DispatchAttemptOut,
    DispatchOut,
    DispatchRequest,
)
from src.api.schemas.types import ULIDStr
from src.core.models.channel import Channel
from src.core.models.dispatch import Dispatch, DispatchAttempt
from src.core.models.template import Template
from src.core.notifications.constants import DispatchAttemptStatus, DispatchStatus
from src.core.notifications.dispatcher import dispatch_to_channel
from src.core.notifications.render import TemplateRenderError, render_template
from src.core.notifications.validate import VariablesValidationError, validate_variables

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


def _attempt_to_out(a: DispatchAttempt) -> DispatchAttemptOut:
    return DispatchAttemptOut(
        channel_id=str(a.channel_id),
        status=a.status,
        reason=a.reason,
        attempt=a.attempt,
        started_at=a.started_at,
        finished_at=a.finished_at,
    )


def _dispatch_to_out(d: Dispatch, attempts: list[DispatchAttempt]) -> DispatchOut:
    return DispatchOut(
        id=str(d.id),
        tenant_id=str(d.tenant_id),
        template_id=str(d.template_id) if d.template_id else None,
        idempotency_key=d.idempotency_key,
        rendered_title=d.rendered_title,
        rendered_body=d.rendered_body,
        status=d.status,
        metadata=d.request_metadata,
        created_at=d.created_at,
        attempts=[_attempt_to_out(a) for a in attempts],
    )


async def _load_owned_channels(
    session: AsyncSession, channel_ids: list[str], tenant_id: str
) -> list[Channel]:
    result = await session.execute(
        select(Channel).where(
            Channel.id.in_(channel_ids), Channel.tenant_id == tenant_id
        )
    )
    channels = list(result.scalars().all())
    found_ids = {str(c.id) for c in channels}
    missing = [cid for cid in channel_ids if cid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"message": "channels not found or not owned by tenant", "channel_ids": missing},
        )
    return channels


async def _load_owned_template(
    session: AsyncSession, template_id: str, tenant_id: str
) -> Template:
    result = await session.execute(
        select(Template).where(Template.id == template_id, Template.tenant_id == tenant_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


async def _attempts_for(
    session: AsyncSession, dispatch_id: str
) -> list[DispatchAttempt]:
    result = await session.execute(
        select(DispatchAttempt)
        .where(DispatchAttempt.dispatch_id == dispatch_id)
        .order_by(DispatchAttempt.started_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=DispatchOut, status_code=202)
async def create_dispatch(
    body: DispatchRequest,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> DispatchOut:
    """Render, validate, dispatch, and log. Returns 202 with the dispatch record."""

    if body.idempotency_key is not None:
        existing = await session.execute(
            select(Dispatch).where(
                Dispatch.tenant_id == tenant_id,
                Dispatch.idempotency_key == body.idempotency_key,
            )
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            return _dispatch_to_out(prior, await _attempts_for(session, prior.id))

    title_src = body.title_template
    body_src = body.body_template
    template: Template | None = None
    if body.template_id is not None:
        template = await _load_owned_template(session, body.template_id, tenant_id)
        title_src = title_src or template.title_template
        body_src = body_src or template.body_template
        try:
            validate_variables(body.variables, template.variables_schema)
        except VariablesValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"section": "variables", "path": exc.path, "message": exc.message},
            ) from exc

    try:
        rendered_title = render_template(title_src, body.variables)
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=422, detail={"section": "title", "message": str(exc)}
        ) from exc
    try:
        rendered_body = render_template(body_src, body.variables)
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=422, detail={"section": "body", "message": str(exc)}
        ) from exc

    channels = await _load_owned_channels(session, body.channel_ids, tenant_id)
    by_id = {str(c.id): c for c in channels}

    dispatch = Dispatch(
        tenant_id=tenant_id,
        template_id=template.id if template else None,
        idempotency_key=body.idempotency_key,
        rendered_title=rendered_title,
        rendered_body=rendered_body,
        variables=body.variables,
        request_metadata=body.metadata,
        status=DispatchStatus.FAILED,  # provisional; updated after attempts
    )
    session.add(dispatch)
    await session.flush()  # populate dispatch.id without releasing the txn

    successes = 0
    attempts: list[DispatchAttempt] = []
    for cid in body.channel_ids:
        channel = by_id[cid]
        started = datetime.now(UTC)
        result = await dispatch_to_channel(
            apprise_url_encrypted=channel.apprise_url_encrypted,
            title=rendered_title,
            body=rendered_body,
        )
        finished = datetime.now(UTC)
        attempt = DispatchAttempt(
            dispatch_id=dispatch.id,
            channel_id=channel.id,
            attempt=1,
            status=(
                DispatchAttemptStatus.SUCCEEDED if result.success else DispatchAttemptStatus.FAILED
            ),
            reason=result.reason,
            started_at=started,
            finished_at=finished,
        )
        session.add(attempt)
        attempts.append(attempt)
        if result.success:
            successes += 1

    if successes == len(channels):
        dispatch.status = DispatchStatus.SUCCEEDED
    elif successes == 0:
        dispatch.status = DispatchStatus.FAILED
    else:
        dispatch.status = DispatchStatus.PARTIAL

    await session.commit()
    await session.refresh(dispatch)
    return _dispatch_to_out(dispatch, attempts)


@router.get("/{dispatch_id}", response_model=DispatchOut)
async def get_dispatch(
    dispatch_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> DispatchOut:
    """Fetch a single dispatch record with its per-channel attempts."""
    result = await session.execute(
        select(Dispatch)
        .where(Dispatch.id == dispatch_id, Dispatch.tenant_id == tenant_id)
        .options(selectinload("*"))
    )
    dispatch = result.scalar_one_or_none()
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return _dispatch_to_out(dispatch, await _attempts_for(session, dispatch.id))
