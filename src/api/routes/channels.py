"""Channel CRUD + per-channel test endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_api_key
from src.api.schemas.channel import (
    ChannelCreate,
    ChannelOut,
    ChannelTestResponse,
    ChannelUpdate,
)
from src.api.schemas.types import ULIDStr
from src.core.crypto import decrypt_apprise_url, encrypt_apprise_url
from src.core.models.channel import Channel
from src.core.notifications.dispatcher import dispatch_to_channel

router = APIRouter(prefix="/channels", tags=["channels"])


def _mask_url(plaintext: str) -> str:
    """Return a masked form of an Apprise URL: scheme + '://' + '***'."""
    if "://" in plaintext:
        scheme, _ = plaintext.split("://", 1)
        return f"{scheme}://***"
    return "***"


def _to_out(c: Channel) -> ChannelOut:
    try:
        plain = decrypt_apprise_url(c.apprise_url_encrypted)
        masked = _mask_url(plain)
    except Exception:
        masked = "<decryption failed>"
    return ChannelOut(
        id=str(c.id),
        tenant_id=str(c.tenant_id),
        name=c.name,
        apprise_url_masked=masked,
        channel_hint=c.channel_hint,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _load_owned(
    session: AsyncSession, channel_id: str, tenant_id: str
) -> Channel:
    result = await session.execute(
        select(Channel).where(Channel.id == channel_id, Channel.tenant_id == tenant_id)
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.get("", response_model=list[ChannelOut])
async def list_channels(
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> list[ChannelOut]:
    """List all channels owned by the calling tenant."""
    result = await session.execute(
        select(Channel).where(Channel.tenant_id == tenant_id).order_by(Channel.created_at)
    )
    return [_to_out(c) for c in result.scalars().all()]


@router.post("", response_model=ChannelOut, status_code=201)
async def create_channel(
    body: ChannelCreate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ChannelOut:
    """Create a new channel; the plaintext Apprise URL is encrypted at rest."""
    channel = Channel(
        tenant_id=tenant_id,
        name=body.name,
        apprise_url_encrypted=encrypt_apprise_url(body.apprise_url),
        channel_hint=body.channel_hint,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return _to_out(channel)


@router.get("/{channel_id}", response_model=ChannelOut)
async def get_channel(
    channel_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ChannelOut:
    """Fetch a single channel; URL returned masked."""
    return _to_out(await _load_owned(session, channel_id, tenant_id))


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: ULIDStr,
    body: ChannelUpdate,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ChannelOut:
    """Partially update a channel; supplied URL is re-encrypted."""
    channel = await _load_owned(session, channel_id, tenant_id)
    payload = body.model_dump(exclude_unset=True)
    if "apprise_url" in payload:
        channel.apprise_url_encrypted = encrypt_apprise_url(payload.pop("apprise_url"))
    for field, value in payload.items():
        setattr(channel, field, value)
    await session.commit()
    await session.refresh(channel)
    return _to_out(channel)


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a channel. Fails if dispatch attempts still reference it."""
    channel = await _load_owned(session, channel_id, tenant_id)
    await session.delete(channel)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Channel cannot be deleted while dispatch attempts reference it.",
        ) from exc


@router.post("/{channel_id}/test", response_model=ChannelTestResponse)
async def test_channel(
    channel_id: ULIDStr,
    tenant_id: str = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ChannelTestResponse:
    """Fire a test notification to a channel. Useful for connection diagnosis."""
    channel = await _load_owned(session, channel_id, tenant_id)
    result = await dispatch_to_channel(
        apprise_url_encrypted=channel.apprise_url_encrypted,
        title="[Notifier] Test notification",
        body=f"This is a test message from Notifier for channel '{channel.name}'.",
    )
    return ChannelTestResponse(success=result.success, reason=result.reason)
