"""Drift tests for scripts/dev_server.sh — the guarded dev-server launch path.

The script must not reimplement the URL parsing in bash. Archiver's bash
``db_name()`` diverged from its python guard on three URL shapes
(CannObserv/archiver#99, commit ee0c952); notifier avoids the whole class of
bug by shelling out to ``src.core.db_safety`` instead.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_SERVER = REPO_ROOT / "scripts" / "dev_server.sh"


def test_dev_server_script_exists_and_is_executable():
    assert DEV_SERVER.is_file()
    assert DEV_SERVER.stat().st_mode & stat.S_IXUSR


def test_dev_server_delegates_the_guard_to_python():
    """One implementation of the URL check, not two."""
    body = DEV_SERVER.read_text()
    assert "src.core.db_safety" in body
    assert "db_name" not in body, "bash must not reimplement the URL parsing"


def test_dev_server_uses_the_safe_env_loading_idiom():
    """``export $(cat … | xargs)`` corrupts values with spaces or quotes."""
    body = DEV_SERVER.read_text()
    assert "set -a" in body
    assert "export $(cat" not in body
    assert "| xargs" not in body


def test_dev_server_checks_the_dev_database_is_migrated():
    """An unmigrated dev DB starts cleanly and 500s on every request (#23)."""
    assert "alembic current" in DEV_SERVER.read_text()


def test_dev_server_refuses_an_unreachable_dev_database():
    env = {
        **os.environ,
        "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1",
        "DEV_DATABASE_URL": "postgresql+asyncpg://notifier@localhost:5432/nope_dev",
        "NOTIFIER_SECRET_KEY": "unused",
    }
    result = subprocess.run(
        [str(DEV_SERVER)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "migration" in (result.stdout + result.stderr).lower()


def test_dev_server_targets_port_9001():
    """Port 9000 belongs to systemd."""
    body = DEV_SERVER.read_text()
    assert "--port 9001" in body
    assert "--port 9000" not in body


def test_dev_server_refuses_a_production_database_url():
    """The failure path exits non-zero before uvicorn is ever reached."""
    env = {
        **os.environ,
        # Skip the env files — they set DEV_DATABASE_URL to the real dev
        # database, which would override the production URL under test.
        "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1",
        "DEV_DATABASE_URL": "postgresql+asyncpg://u@h/notifier",
        "NOTIFIER_SECRET_KEY": "unused",
    }
    env.pop("NOTIFIER_ALLOW_PROD_DB", None)
    # Short timeout on purpose: if the guard ever stops refusing, uvicorn
    # starts and this must fail fast rather than hang the suite.
    result = subprocess.run(
        [str(DEV_SERVER)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "notifier" in combined
    assert "uvicorn running" not in combined.lower()


def test_dev_server_refuses_when_no_dev_database_is_configured():
    env = {**os.environ}
    env.pop("DEV_DATABASE_URL", None)
    env.pop("NOTIFIER_ALLOW_PROD_DB", None)
    result = subprocess.run(
        [str(DEV_SERVER)],
        cwd=REPO_ROOT,
        env={**env, "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "DEV_DATABASE_URL" in result.stdout + result.stderr


DOCS = [
    "AGENTS.md",
    "README.md",
    "docs/COMMANDS.md",
    "docs/DEPLOYMENT.md",
    "clients/python/README.md",
]


@pytest.mark.parametrize("doc", DOCS)
def test_docs_do_not_carry_the_unguarded_recipe(doc):
    """No doc may pair a prod env load with a hand-run uvicorn."""
    body = (REPO_ROOT / doc).read_text()
    assert "export $(cat /etc/notifier/.env" not in body
    if "uvicorn src.api.main:app" in body:
        assert "dev_server.sh" in body


@pytest.mark.parametrize("doc", DOCS)
def test_docs_guard_both_env_files(doc):
    """Sourcing an absent /etc/notifier/.env must not break a fresh clone."""
    for line in (REPO_ROOT / doc).read_text().splitlines():
        if "/etc/notifier/.env" not in line or "set -a" not in line:
            continue
        assert "[ -r /etc/notifier/.env ]" in line, (
            f"{doc}: sources /etc/notifier/.env unguarded: {line.strip()}"
        )
