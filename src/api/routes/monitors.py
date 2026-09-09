"""Monitor CRUD and the check-in endpoint — the dead-man's timer's front door (#56).

A consumer POSTs a check-in **every tick, regardless of findings**. The
arrival resets the timer; the ``status`` field says whether the contents also
warrant a notification. What makes a report worth alerting on is the
consumer's judgement — a broker maps its own ``finding_count > 0`` onto
``alert`` — because the alternative is notifier learning a consumer's
taxonomy.

The absence half lives in ``src/core/monitors.py`` and runs from a systemd
timer, not from this process.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_api_key
from src.api.schemas.dispatch import DispatchOut
from src.api.schemas.monitor import (
    CheckinRequest,
    CheckinResponse,
    MonitorCreate,
    MonitorOut,
    MonitorUpdate,
)
from src.api.schemas.types import ULIDStr
from src.core.models.channel import Channel
from src.core.models.monitor import Monitor
from src.core.models.template import Template
from src.core.monitors import (
    CheckinStatus,
    MonitorState,
    deadline_for,
    recovery_notification,
    resolve_channels,
)
from src.core.notifications.delivery import deliver
from src.core.notifications.render import TemplateRenderError, render_template
from src.core.notifications.validate import (
    SchemaDocumentError,
    VariablesValidationError,
    validate_variables,
)

router = APIRouter(prefix="/monitors", tags=["monitors"])


def _to_out(m: Monitor) -> MonitorOut:
    return MonitorOut(
        id=str(m.id),
        tenant_id=str(m.tenant_id),
        name=m.name,
        enabled=m.enabled,
        interval_seconds=m.interval_seconds,
        grace_seconds=m.grace_seconds,
        renotify_seconds=m.renotify_seconds,
        channel_ids=list(m.channel_ids),
        template_id=str(m.template_id) if m.template_id else None,
        title_template=m.title_template,
        body_template=m.body_template,
        state=m.state,
        last_checkin_at=m.last_checkin_at,
        last_status=m.last_status,
        last_variables=m.last_variables,
        last_alert_at=m.last_alert_at,
        next_deadline_at=deadline_for(m),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


async def _load_owned(session: AsyncSession, monitor_id: str, tenant_id: str) -> Monitor:
    result = await session.execute(
        select(Monitor).where(Monitor.id == monitor_id, Monitor.tenant_id == tenant_id)
    )
    monitor = result.scalar_one_or_none()
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


async def _owned_channels(
    session: AsyncSession, channel_ids: list[str], tenant_id: str
) -> list[Channel]:
    """Resolve channel ids in the order given, 404ing on any not owned.

    ``channel_ids`` is stored as an array rather than a join table, so this is
    the only place ownership is enforced — checked on every write, not just at
    create.
    """
    if not channel_ids:
        return []
    result = await session.execute(
        select(Channel).where(Channel.id.in_(channel_ids), Channel.tenant_id == tenant_id)
    )
    by_id = {str(c.id): c for c in result.scalars().all()}
    missing = [cid for cid in channel_ids if cid not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"message": "channels not found or not owned by tenant", "channel_ids": missing},
        )
    return [by_id[cid] for cid in channel_ids]


async def _owned_template(session: AsyncSession, template_id: str, tenant_id: str) -> Template:
    result = await session.execute(
        select(Template).where(Template.id == template_id, Template.tenant_id == tenant_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("", response_model=list[MonitorOut])
async def list_monitors(
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> list[MonitorOut]:
    """List all monitors owned by the calling tenant."""
    result = await session.execute(
        select(Monitor).where(Monitor.tenant_id == tenant_id).order_by(Monitor.created_at)
    )
    return [_to_out(m) for m in result.scalars().all()]


@router.post("", response_model=MonitorOut, status_code=201)
async def create_monitor(
    body: MonitorCreate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> MonitorOut:
    """Create a monitor. It starts ``pending`` and its clock starts now.

    The deadline is anchored on creation until the first check-in arrives, so
    a probe that is configured here but never wired up on the consumer's side
    alerts rather than sitting silent.
    """
    await _owned_channels(session, body.channel_ids, tenant_id)
    if body.template_id is not None:
        await _owned_template(session, body.template_id, tenant_id)

    monitor = Monitor(tenant_id=tenant_id, **body.model_dump())
    session.add(monitor)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail=f"A monitor named '{body.name}' already exists."
        ) from exc
    await session.refresh(monitor)
    return _to_out(monitor)


@router.get("/{monitor_id}", response_model=MonitorOut)
async def get_monitor(
    monitor_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> MonitorOut:
    """Fetch a single monitor, including its last report and next deadline."""
    return _to_out(await _load_owned(session, monitor_id, tenant_id))


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def update_monitor(
    monitor_id: ULIDStr,
    body: MonitorUpdate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> MonitorOut:
    """Partially update a monitor. ``enabled: false`` pauses the timer."""
    monitor = await _load_owned(session, monitor_id, tenant_id)
    payload = body.model_dump(exclude_unset=True)
    if payload.get("channel_ids"):
        await _owned_channels(session, payload["channel_ids"], tenant_id)
    if payload.get("template_id"):
        await _owned_template(session, payload["template_id"], tenant_id)
    for field, value in payload.items():
        setattr(monitor, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="That monitor name is already taken.") from exc
    await session.refresh(monitor)
    return _to_out(monitor)


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(
    monitor_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a monitor. Its past dispatches are kept."""
    monitor = await _load_owned(session, monitor_id, tenant_id)
    await session.delete(monitor)
    await session.commit()


@router.post("/{monitor_id}/checkin", response_model=CheckinResponse, status_code=202)
async def checkin(
    monitor_id: ULIDStr,
    body: CheckinRequest,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> CheckinResponse:
    """Record a check-in, and dispatch anything it warrants.

    Send one every tick whether or not there is anything to report. Zero
    findings and zero traffic is what a dead probe looks like too, so the
    report's *arrival* is the part notifier cannot infer.
    """
    monitor = await _load_owned(session, monitor_id, tenant_id)
    now = datetime.now(UTC)
    previous_state = monitor.state
    dispatches: list[DispatchOut] = []

    # Render before recording anything: a report that violates the template's
    # schema is the consumer's bug, and a 422 should leave the monitor exactly
    # as it was rather than half-updated.
    rendered: tuple[str, str] | None = None
    if body.status == CheckinStatus.ALERT:
        rendered = await _render_report(session, monitor, body, tenant_id)

    # Lenient, unlike the write paths: `channel_ids` is an array, not a
    # foreign key, so a deleted channel would 404 every check-in from here on
    # — turning a misconfigured destination into a fabricated outage. Deliver
    # to whatever still exists and let the dispatch record show the rest.
    channels = await resolve_channels(session, monitor)

    if previous_state == MonitorState.MISSING:
        # Fired before last_checkin_at moves, so the notice can quote the
        # length of the silence that just ended.
        title, message = recovery_notification(monitor, now)
        dispatches.append(
            await _deliver_out(
                session, monitor, channels, title, message, reason="recovered", tenant_id=tenant_id
            )
        )

    monitor.last_checkin_at = now
    monitor.last_status = body.status
    monitor.last_variables = body.variables
    monitor.state = MonitorState.OK

    if rendered is not None:
        title, message = rendered
        dispatches.append(
            await _deliver_out(
                session,
                monitor,
                channels,
                title,
                message,
                reason="report",
                tenant_id=tenant_id,
                variables=body.variables,
                metadata=body.metadata,
            )
        )

    await session.commit()
    await session.refresh(monitor)
    return CheckinResponse(
        monitor_id=str(monitor.id),
        previous_state=previous_state,
        state=monitor.state,
        last_checkin_at=monitor.last_checkin_at,
        next_deadline_at=deadline_for(monitor),
        dispatches=dispatches,
    )


async def _render_report(
    session: AsyncSession, monitor: Monitor, body: CheckinRequest, tenant_id: str
) -> tuple[str, str]:
    """Render the monitor's alert template against the reported variables.

    Only reached for an ``alert`` check-in. An ``ok`` heartbeat renders
    nothing and so is never schema-checked: rejecting the heartbeat over its
    payload would silence the timer to protect a notification that was never
    going to be sent.
    """
    title_src = monitor.title_template
    body_src = monitor.body_template
    if monitor.template_id is not None:
        template = await _owned_template(session, str(monitor.template_id), tenant_id)
        title_src = title_src or template.title_template
        body_src = body_src or template.body_template
        try:
            validate_variables(body.variables, template.variables_schema)
        except SchemaDocumentError as exc:
            raise HTTPException(
                status_code=422,
                detail={"section": "variables_schema", "path": exc.path, "message": exc.message},
            ) from exc
        except VariablesValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"section": "variables", "path": exc.path, "message": exc.message},
            ) from exc

    try:
        return (
            render_template(title_src, body.variables),
            render_template(body_src, body.variables),
        )
    except TemplateRenderError as exc:
        raise HTTPException(
            status_code=422, detail={"section": "template", "message": str(exc)}
        ) from exc


async def _deliver_out(
    session: AsyncSession,
    monitor: Monitor,
    channels: list[Channel],
    title: str,
    message: str,
    *,
    reason: str,
    tenant_id: str,
    variables: dict | None = None,
    metadata: dict | None = None,
) -> DispatchOut:
    delivery = await deliver(
        session,
        tenant_id=tenant_id,
        channels=channels,
        rendered_title=title,
        rendered_body=message,
        variables=variables,
        metadata={**(metadata or {}), "monitor_id": str(monitor.id), "reason": reason},
        template_id=str(monitor.template_id) if monitor.template_id else None,
    )
    return DispatchOut.from_models(delivery.dispatch, delivery.attempts)
