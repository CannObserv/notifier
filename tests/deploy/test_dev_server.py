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


def test_dev_server_delegates_env_loading_to_the_shared_loader():
    """One env-loading recipe, in scripts/load_env.sh — not a second copy."""
    body = DEV_SERVER.read_text()
    assert "load_env.sh" in body
    assert "export $(cat" not in body
    assert "| xargs" not in body


def test_dev_server_sources_the_loader_by_resolved_path():
    """Not repo-root-relative — that silently couples it to the earlier cd."""
    body = DEV_SERVER.read_text()
    assert '. "$(dirname "${BASH_SOURCE[0]}")/load_env.sh"' in body
    assert ". scripts/load_env.sh" not in body


def test_dev_server_checks_the_dev_database_is_migrated():
    """An unmigrated dev DB starts cleanly and 500s on every request (#23)."""
    assert "alembic current" in DEV_SERVER.read_text()


def test_dev_server_refuses_an_unreachable_dev_database():
    env = {
        **os.environ,
        "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1",
        # Port 1 is unroutable, so the connection failure is structural rather
        # than depending on no database named nope_dev ever existing.
        "DEV_DATABASE_URL": "postgresql+asyncpg://notifier@localhost:1/nope_dev",
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


def test_dev_server_binds_the_tailnet_address_not_a_wildcard(tmp_path):
    """#43 D3 — the dev endpoint carries real consumer traffic from watcher.

    Asserts the resolved address reaches uvicorn, so a future edit cannot
    quietly reintroduce ``--host 0.0.0.0`` while the probe still runs.
    """
    line = _run_dev_server(tmp_path, NOTIFIER_BIND_HOST="100.64.1.2")
    assert "--host 100.64.1.2" in line
    assert "0.0.0.0" not in line


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


def _fake_uv_path(tmp_path):
    """A `uv` that echoes its arguments instead of running anything.

    Lets the launch path be exercised end to end — guard call, migration
    check, final uvicorn line — with no database and no server. The migration
    check only asks whether `alembic current` printed anything, so echoing
    satisfies it.
    """
    fake = tmp_path / "uv"
    fake.write_text('#!/usr/bin/env bash\necho "uv $*"\n')
    fake.chmod(0o755)
    return tmp_path


def _run_dev_server(tmp_path, **overrides):
    env = {
        **os.environ,
        "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1",
        "DEV_DATABASE_URL": "postgresql+asyncpg://u@h/notifier_dev",
        "NOTIFIER_SECRET_KEY": "unused",
        # CI has no tailnet, so the real probe would burn its full wait and
        # then fail every test in this file. The override exists for exactly
        # this; test_systemd_unit.py asserts no unit or env file carries it.
        "NOTIFIER_BIND_HOST": "127.0.0.1",
        "PATH": f"{_fake_uv_path(tmp_path)}:{os.environ['PATH']}",
        **overrides,
    }
    env.pop("NOTIFIER_ALLOW_PROD_DB", None)
    result = subprocess.run(
        [str(DEV_SERVER)], cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    uvicorn_line = next((line for line in result.stdout.splitlines() if "uvicorn" in line), None)
    assert uvicorn_line is not None, f"never reached uvicorn:\n{result.stdout}{result.stderr}"
    return uvicorn_line


def _uv_call_environments(tmp_path, **overrides):
    """Run the script with a `uv` that records the environment of every call.

    Returns ``{first argument after run: {name: value}}``, one entry per
    ``uv run``: ``python`` (the db_safety guard), ``alembic`` and ``uvicorn``.
    The dump path is baked into the shim, not passed in a variable, because
    a variable is exactly what the allowlist under test would strip.
    """
    shim_dir = tmp_path / "recording"  # _run_dev_server rewrites tmp_path/uv
    shim_dir.mkdir()
    dump = tmp_path / "uv-env.dump"
    fake = shim_dir / "uv"
    fake.write_text(f'#!/usr/bin/env bash\n{{ echo "### $2"; env; }} >> "{dump}"\necho "uv $*"\n')
    fake.chmod(0o755)
    _run_dev_server(tmp_path, PATH=f"{shim_dir}:{os.environ['PATH']}", **overrides)
    calls = {}
    for block in dump.read_text().split("### ")[1:]:
        command, *lines = block.splitlines()
        calls[command] = dict(line.split("=", 1) for line in lines if "=" in line)
    return calls


# Names the dev server's process does not read, planted the way a shell that
# already sourced load_env.sh would hand them over — the by-hand path, where
# the credentials come from the parent environment and not from the loader.
PLANTED = {
    "GH_TOKEN_X": "planted",
    "ANTHROPIC_API_KEY": "planted",
    "EXE_API_TOKEN": "planted",
    "DEV_TENANT_API_KEY": "planted",
    "TEST_DATABASE_URL": "postgresql+asyncpg://u@h/notifier_test",
    # uv reads this one itself, which is why UV_* is allowed by name, not prefix.
    "UV_PUBLISH_TOKEN": "planted",
}


def test_dev_server_keeps_credentials_from_every_uv_call(tmp_path):
    """#158 — notifier-dev held every repo .env credential through this script.

    An allowlist at each `uv run`, not a denylist, so a token added to the
    repo .env tomorrow stays out without anyone remembering to list it.
    """
    calls = _uv_call_environments(tmp_path, **PLANTED)
    assert set(calls) == {"python", "alembic", "uvicorn"}
    for command, env in calls.items():
        leaked = sorted(set(PLANTED) & set(env))
        assert not leaked, f"uv run {command} received {leaked}"
        # A redundant copy of DATABASE_URL, and a second credential besides.
        assert "DEV_DATABASE_URL" not in env, command


def test_dev_server_passes_what_the_server_reads(tmp_path):
    """Getting the allowlist wrong takes down the endpoint consumers use.

    Each name here is read by the exec'd process: DATABASE_URL by the engine
    and alembic, NOTIFIER_SECRET_KEY by crypto, BUILD_ID by /health,
    NOTIFIER_APP_URL by the dispatcher, NOTIFIER_AUDIT_SOCKET by main.py's
    audit logging, and PATH and HOME by uv itself.
    """
    wanted = {
        "NOTIFIER_SECRET_KEY": "unused",
        "BUILD_ID": "abc1234",
        "NOTIFIER_APP_URL": "https://example.test",
        "NOTIFIER_AUDIT_SOCKET": "/run/test.sock",
    }
    env = _uv_call_environments(tmp_path, **wanted)["uvicorn"]
    assert env["DATABASE_URL"] == "postgresql+asyncpg://u@h/notifier_dev"
    for name, value in wanted.items():
        assert env.get(name) == value, name
    assert env["PATH"].startswith(f"{tmp_path / 'recording'}:")
    assert env["HOME"] == os.environ["HOME"]


def test_dev_server_never_passes_the_production_opt_in(tmp_path):
    """The unset at the top and the allowlist at each call agree."""
    for command, env in _uv_call_environments(tmp_path, NOTIFIER_ALLOW_PROD_DB="1").items():
        assert "NOTIFIER_ALLOW_PROD_DB" not in env, command


def test_dev_server_reloads_by_default(tmp_path):
    """The hand-run server is an editing loop; keep --reload there."""
    assert "--reload" in _run_dev_server(tmp_path)


def test_dev_server_reload_can_be_switched_off(tmp_path):
    """deploy/notifier-dev.service sets this (#24).

    Under systemd the reloader is wrong twice over: an edit mid-request drops
    a consumer's connection, and a syntax error on main leaves the reloader
    wedged and *running*, so no Restart= policy fires and the endpoint
    is silently dead.
    """
    assert "--reload" not in _run_dev_server(tmp_path, NOTIFIER_DEV_RELOAD="0")


def test_dev_server_still_guards_when_the_reloader_is_off(tmp_path):
    """The toggle must not become a way around the checks."""
    line = _run_dev_server(tmp_path, NOTIFIER_DEV_RELOAD="0")
    assert "--port 9001" in line


def test_dev_server_refuses_without_the_encryption_key():
    """A missing NOTIFIER_SECRET_KEY must fail at startup, not at dispatch.

    No fake-`uv` shim here: the check sits ahead of the first `uv` call, so
    the script never reaches one. If that ordering ever changes, this test
    starts invoking the real `uv` and slows down — which is the signal to
    move the check back.

    scripts/load_env.sh skips /etc/notifier/.env silently when it is not
    readable — its parser returns early on `[ -r … ] || return 0`. The file
    is exedev-owned today, so it loads; at root:root 0640 it would vanish
    from the environment without a word.
    The service would still start and still pass /ready, because the database
    URL comes from the repo .env, and would then fail on the first channel
    decrypt. A health check that reports green while the one thing the service
    exists to do is broken is worse than no health check.
    """
    env = {
        **os.environ,
        "NOTIFIER_DEV_SERVER_SKIP_ENV_FILES": "1",
        "DEV_DATABASE_URL": "postgresql+asyncpg://u@h/notifier_dev",
    }
    env.pop("NOTIFIER_SECRET_KEY", None)
    env.pop("NOTIFIER_ALLOW_PROD_DB", None)
    result = subprocess.run(
        [str(DEV_SERVER)], cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "NOTIFIER_SECRET_KEY" in combined
    assert "uvicorn" not in combined, "must refuse before starting the server"
