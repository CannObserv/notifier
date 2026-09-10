"""Health and readiness check endpoints."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session
from src.api.schemas.health import HealthResponse, ReadyResponse
from src.core.db_safety import database_name, is_non_production, serving_production

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


def _resolve_database() -> tuple[str, str]:
    """The database this process serves, and how it classifies.

    Fails soft, unlike :mod:`src.core.db_safety` itself. ``database_name()``
    raises on any URL it cannot read, and letting that escape at import time
    would mean the app never starts — a worse outcome than the ambiguity this
    reports. An unreadable URL is therefore ``"unknown"`` and, following
    ``serving_production()``, the conservative ``"production"``.

    The name is not redundant with the classification: every non-suffixed name
    classifies as ``production``, so ``notifier`` and ``notifier_staging`` are
    one value there and two here.
    """
    try:
        name = database_name(os.environ.get("DATABASE_URL", ""))
    except ValueError:
        name = "unknown"
    return name, "production" if serving_production() else "development"


BUILD_ID = _resolve_build_id()
DATABASE, ENVIRONMENT = _resolve_database()


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness probe — confirms the app process is running. No DB call.

    Unauthenticated, deliberately: the case this serves is a consumer wiring
    up for the first time, before it has a key that works. Nothing here is a
    secret — the database names and the ``_dev``/``_test`` suffix rule are
    published in this repo's AGENTS.md, and both ports bind the tailnet
    address alone behind an ACL, never ``0.0.0.0``.

    Read from the configured URL, so it stays a no-DB liveness probe; ``/ready``
    reports the database actually connected.
    """
    return HealthResponse(status="ok", build=BUILD_ID, database=DATABASE, environment=ENVIRONMENT)


@router.get("/ready", response_model=ReadyResponse)
async def ready(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """Readiness probe — checks DB connectivity. Returns 503 on failure.

    ``current_database()`` rather than ``SELECT 1``: same round trip, and it
    names the database on the other end of the connection instead of the one
    ``DATABASE_URL`` claims. ``/health`` and ``/ready`` disagreeing is the
    only signal that those two have diverged.
    """
    try:
        result = await session.execute(text("SELECT current_database()"))
        name = str(result.scalar_one())
        payload = ReadyResponse(
            status="ready",
            db=True,
            database=name,
            environment="development" if is_non_production(name) else "production",
        )
        return JSONResponse(status_code=200, content=payload.model_dump())
    except SQLAlchemyError:
        payload = ReadyResponse(status="not_ready", db=False)
        return JSONResponse(status_code=503, content=payload.model_dump())
