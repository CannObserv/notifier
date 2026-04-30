"""Shared test fixtures — async database session and FastAPI TestClient."""

import hashlib
import os
import secrets
from collections.abc import AsyncGenerator

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.api.deps import get_db_session
from src.core.models import ApiKey, Base, Tenant

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL environment variable is not set. "
        "Load env: export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)"
    )

# Ensure crypto has a key in test env even when /etc/notifier/.env is not loaded.
os.environ.setdefault("NOTIFIER_SECRET_KEY", Fernet.generate_key().decode())


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession]:
    """Per-test session wrapped in a savepoint that rolls back on teardown."""
    async with test_engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        nested = await conn.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(db_session, transaction):
            nonlocal nested
            if not nested.is_active:
                nested = conn.sync_connection.begin_nested()

        yield session

        await session.close()
        await txn.rollback()


@pytest.fixture
async def tenant(db_session) -> Tenant:
    """Create a fresh tenant for the test."""
    t = Tenant(name=f"test-{secrets.token_hex(4)}")
    db_session.add(t)
    await db_session.flush()
    return t


@pytest.fixture
async def api_key(db_session, tenant) -> tuple[str, ApiKey]:
    """Create a test ApiKey; returns (raw_key, ApiKey)."""
    raw = "nk_" + secrets.token_urlsafe(16)
    key = ApiKey(
        tenant_id=tenant.id,
        label="test",
        key_prefix=raw[:8],
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
    )
    db_session.add(key)
    await db_session.flush()
    return raw, key


@pytest.fixture
async def client(test_engine, db_session) -> AsyncGenerator[AsyncClient]:
    """An AsyncClient wired to the FastAPI app with the savepointed db_session."""
    from src.api.main import app

    async def override_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
