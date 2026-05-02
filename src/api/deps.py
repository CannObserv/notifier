"""FastAPI dependencies — database session and API-key authentication."""

import hashlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session_factory
from src.core.models.api_key import ApiKey


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session."""
    async with get_session_factory()() as session:
        yield session


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    raw_key: str | None = Depends(api_key_header),
    session: AsyncSession = Depends(get_db_session),
) -> str:
    """Validate X-API-Key header; return ``tenant_id`` on success.

    Raises 403 when the header is absent and 401 when the key is invalid or
    not found. Updates ``last_used_at`` on each successful authentication.
    """
    if raw_key is None:
        raise HTTPException(status_code=403, detail="Not authenticated")
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    api_key.last_used_at = datetime.now(UTC)
    await session.commit()
    return str(api_key.tenant_id)
