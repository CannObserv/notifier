"""Shared fixtures for SDK tests."""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
NOTIFIER_URL = os.environ.get("NOTIFIER_URL", "http://localhost:9001")


@pytest.fixture(scope="session")
def notifier_url() -> str:
    return NOTIFIER_URL


@pytest.fixture(scope="session")
def tenant_credentials() -> tuple[str, str]:
    """Provision a tenant + API key via scripts/seed_tenant.py.

    The seed script needs notifier server deps (sqlalchemy, asyncpg). It runs
    via ``uv run`` from the notifier repo root so it picks up the server's
    virtualenv, not the SDK's. Skips integration tests if the seed script
    can't run (e.g. no DB env, no DATABASE_URL)."""
    if os.environ.get("NOTIFIER_TENANT_ID") and os.environ.get("NOTIFIER_API_KEY"):
        return os.environ["NOTIFIER_TENANT_ID"], os.environ["NOTIFIER_API_KEY"]
    try:
        result = subprocess.run(
            ["uv", "run", "python", "scripts/seed_tenant.py", "sdk-integration", "smoke"],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        pytest.skip(f"could not seed tenant: {exc}\n{stderr}")
    out = result.stdout
    tid = re.search(r"tenant_id=(\S+)", out)
    key = re.search(r"raw_key=(\S+)", out)
    if not (tid and key):
        pytest.skip(f"seed script output unparseable: {out!r}")
    return tid.group(1), key.group(1)
