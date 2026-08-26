"""Shared test fixtures — async database session and FastAPI TestClient."""

import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass

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
        "TEST_DATABASE_URL environment variable is not set. Load env:  . scripts/load_env.sh"
    )

# Pin DATABASE_URL at the test database for the whole session, before any
# fixture runs. Without this, a pytest run in a shell that sourced
# /etc/notifier/.env leaves DATABASE_URL pointing at production for any code
# that reads it directly (issue #22; archiver hit this as archiver#157).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

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


@pytest.fixture(scope="session")
def closed_port() -> Iterator[int]:
    """An address where a connection is refused immediately.

    Holds the socket for the whole session without ever calling listen().
    Binding and releasing would only leave the port *unclaimed*: `sink_server`
    binds port 0 in the same session and the kernel is free to hand it exactly
    this number, at which point the "closed" port is a live HTTP server and
    the failure-path tests fail for reasons that look nothing like the cause.
    A bound-but-unlistening port answers RST, so connecting still refuses
    immediately rather than hanging.

    Dispatch tests need a target that fails fast and locally. They used
    `json://example.com`, which made every `pytest` run POST notification
    payloads to a third-party host — real DNS, real TCP, and slower offline
    for an outcome no assertion looked at.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        yield s.getsockname()[1]


@dataclass
class Sink:
    """A local HTTP endpoint Apprise can deliver to, and what it received."""

    port: int
    received: list[dict]


@pytest.fixture(scope="session")
def sink_server() -> Iterator[Sink]:
    """A delivery target that succeeds, and records what arrived.

    Two jobs. It makes a *successful* attempt possible without leaving the
    machine — which is what puts a mixed-outcome dispatch, and therefore the
    `partial` status, within reach of a test. And it lets a test assert on the
    bytes that actually went out, rather than on the kwargs of a mock: the
    gap that hid #25 for the lifetime of the feature.
    """
    received: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                received.append(json.loads(raw))
            except ValueError:
                received.append({"_raw": raw.decode(errors="replace")})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args) -> None:
            """Silence the default stderr access log."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield Sink(port=server.server_address[1], received=received)
    server.shutdown()
    server.server_close()
