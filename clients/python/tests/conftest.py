"""Shared fixtures for SDK tests."""

import os
import re
import subprocess
import sys
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

    Skips integration tests if the seed script can't run (e.g. no DB env)."""
    if os.environ.get("NOTIFIER_TENANT_ID") and os.environ.get("NOTIFIER_API_KEY"):
        return os.environ["NOTIFIER_TENANT_ID"], os.environ["NOTIFIER_API_KEY"]
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "seed_tenant.py"),
             "sdk-integration", "smoke"],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"could not seed tenant: {exc}")
    out = result.stdout
    tid = re.search(r"tenant_id=(\S+)", out)
    key = re.search(r"raw_key=(\S+)", out)
    if not (tid and key):
        pytest.skip(f"seed script output unparseable: {out!r}")
    return tid.group(1), key.group(1)
