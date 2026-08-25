"""Health and readiness check endpoints."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session

router = APIRouter(tags=["health"])


def _resolve_build_id() -> str:
    """The commit this process is serving, or ``"dev"`` when unstamped.

    Blank counts as unstamped. Both systemd units write the stamp with
    ``echo BUILD_ID=$(git rev-parse --short HEAD)``, and ``echo`` exits 0 even
    when the substitution comes back empty — so a failing ``git`` produces a
    successful ExecStartPre and a ``BUILD_ID=`` line. ``os.environ.get`` with a
    default would hand that straight through, and ``{"build": ""}`` reads as a
    broken health endpoint rather than a missing build stamp.
    """
    return os.environ.get("BUILD_ID", "").strip() or "dev"


BUILD_ID = _resolve_build_id()


@router.get("/health")
async def health() -> dict:
    """Liveness probe — confirms the app process is running. No DB call."""
    return {"status": "ok", "build": BUILD_ID}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """Readiness probe — checks DB connectivity. Returns 503 on failure."""
    try:
        await session.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready", "db": True})
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "not_ready", "db": False})
