"""Shared fixtures for SDK integration tests.

Gated on ``TEST_DATABASE_URL``. The fixture heals any tables left behind by a
prior session whose teardown failed, creates the schema, spawns a uvicorn
subprocess wired to the test DB on an ephemeral port, seeds a tenant against
the same DB, and tears all of it down on session exit. Every subprocess
receives ``DATABASE_URL=$TEST_DATABASE_URL`` and a fresh per-session
``NOTIFIER_SECRET_KEY`` so production cannot be touched even if
``/etc/notifier/.env`` was exported into the parent shell.
"""

import base64
import os
import re
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Subprocess + readiness timeouts. Tuned for a quiet dev VM; bump these if a
# slow worker or remote DB starts brushing against them.
SCHEMA_TIMEOUT_SECONDS = 30.0
SEED_TIMEOUT_SECONDS = 30.0
UVICORN_READY_TIMEOUT_SECONDS = 15.0
UVICORN_SHUTDOWN_TIMEOUT_SECONDS = 5.0
HEALTH_PROBE_TIMEOUT_SECONDS = 1.0
HEALTH_POLL_INTERVAL_SECONDS = 0.2


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def _test_db_url() -> str:
    db = os.environ.get("TEST_DATABASE_URL")
    if not db:
        pytest.skip(
            "TEST_DATABASE_URL not set — refusing to run integration tests "
            "against an unconfigured (or production) database. Set "
            "TEST_DATABASE_URL in repo .env."
        )
    return db


@pytest.fixture(scope="session")
def _server_env(_test_db_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": _test_db_url,
        "NOTIFIER_SECRET_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    }


_SCHEMA_SCRIPT = """
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from src.core.models import Base

ACTIONS = {"create_all": Base.metadata.create_all, "drop_all": Base.metadata.drop_all}

async def main(action):
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(ACTIONS[action])
    await engine.dispose()

asyncio.run(main(sys.argv[1]))
"""


def _run_schema(action: Literal["create_all", "drop_all"], env: dict[str, str]) -> None:
    try:
        subprocess.run(
            ["uv", "run", "python", "-c", _SCHEMA_SCRIPT, action],
            cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True,
            timeout=SCHEMA_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"schema {action} failed:\n{exc.stderr or exc.stdout or exc}")
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"schema {action} timed out after {SCHEMA_TIMEOUT_SECONDS}s:\n"
            f"{exc.stderr or exc.stdout or exc}"
        )


@pytest.fixture(scope="session")
def _heal_test_db(_server_env: dict[str, str]) -> None:
    """Drop any tables left behind by a prior session whose teardown failed.

    ``create_all`` doesn't migrate existing tables — a leftover schema would
    silently mask model drift. Running ``drop_all`` first guarantees the
    subsequent ``create_all`` builds fresh DDL from the current models.
    Idempotent on an empty DB.
    """
    _run_schema("drop_all", _server_env)


@pytest.fixture(scope="session")
def _test_db_schema(_server_env: dict[str, str], _heal_test_db: None):
    _run_schema("create_all", _server_env)
    yield
    _run_schema("drop_all", _server_env)


def _read_stderr(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except OSError as exc:
        return f"<could not read {path}: {exc}>"


@pytest.fixture(scope="session")
def notifier_url(_server_env, _test_db_schema):
    """Spawn a uvicorn subprocess on an ephemeral port wired to the test DB.

    Subprocess stderr is redirected to a tempfile so we can surface it in
    error messages on early exit or readiness timeout, without risking the
    pipe-buffer deadlock that ``stderr=PIPE`` would create.
    """
    port = _free_port()
    stderr_fd, stderr_path = tempfile.mkstemp(prefix="uvicorn-", suffix=".log")
    try:
        try:
            proc = subprocess.Popen(
                [
                    "uv", "run", "uvicorn", "src.api.main:app",
                    "--host", "127.0.0.1", "--port", str(port),
                ],
                cwd=REPO_ROOT, env=_server_env,
                stdout=subprocess.DEVNULL, stderr=stderr_fd,
            )
        finally:
            os.close(stderr_fd)
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + UVICORN_READY_TIMEOUT_SECONDS
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"uvicorn exited early with code {proc.returncode}\n"
                        f"--- stderr ---\n{_read_stderr(stderr_path)}"
                    )
                try:
                    if httpx.get(
                        f"{base}/health", timeout=HEALTH_PROBE_TIMEOUT_SECONDS
                    ).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
            else:
                raise RuntimeError(
                    f"uvicorn did not become ready within {UVICORN_READY_TIMEOUT_SECONDS}s\n"
                    f"--- stderr ---\n{_read_stderr(stderr_path)}"
                )
            yield base
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=UVICORN_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        try:
            os.unlink(stderr_path)
        except OSError:
            pass


@pytest.fixture(scope="session")
def tenant_credentials(_server_env, _test_db_schema) -> tuple[str, str]:
    """Seed a tenant + API key against the test DB via scripts/seed_tenant.py.

    By the time this runs the env is fully provisioned (TEST_DATABASE_URL
    gated, schema created), so a seed failure means something is genuinely
    broken — fail loudly rather than skip silently.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "python", "scripts/seed_tenant.py", "sdk-integration", "smoke"],
            capture_output=True, text=True, check=True,
            cwd=REPO_ROOT, env=_server_env, timeout=SEED_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"seed_tenant.py failed:\n{exc.stderr or exc.stdout or exc}")
    except FileNotFoundError as exc:
        pytest.fail(f"uv not on PATH: {exc}")
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"seed_tenant.py timed out after {SEED_TIMEOUT_SECONDS}s:\n"
            f"{exc.stderr or exc.stdout or exc}"
        )
    out = result.stdout
    tid = re.search(r"tenant_id=(\S+)", out)
    key = re.search(r"raw_key=(\S+)", out)
    if not (tid and key):
        pytest.fail(f"seed script output unparseable: {out!r}")
    return tid.group(1), key.group(1)
