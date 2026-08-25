"""Drift tests for scripts/load_env.sh — the one env-loading recipe.

The guarded idiom was 96 characters and appeared nine times across five docs.
That is long enough that people shorten it when copying, and the shortened
form is the unsafe one. One short sourceable line keeps the copyable surface
small and gives these tests a single target.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADER = REPO_ROOT / "scripts" / "load_env.sh"
DOCS = [
    "AGENTS.md",
    "README.md",
    "docs/COMMANDS.md",
    "docs/DEPLOYMENT.md",
    "clients/python/README.md",
]


def test_loader_exists():
    assert LOADER.is_file()


def test_loader_guards_both_env_files():
    """A fresh clone has neither file; sourcing must not fail."""
    body = LOADER.read_text()
    assert "[ -r /etc/notifier/.env ]" in body
    assert "set -a" in body
    assert "| xargs" not in body
    assert "export $(cat" not in body


def test_loader_resolves_the_repo_env_regardless_of_cwd():
    """clients/python sources it from a subdirectory."""
    assert "BASH_SOURCE" in LOADER.read_text()


def test_loader_is_sourceable_from_a_subdirectory():
    result = subprocess.run(
        ["bash", "-c", f". {LOADER} && echo OK"],
        cwd=REPO_ROOT / "clients" / "python",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_loader_succeeds_when_neither_env_file_exists():
    """Sourcing under `set -e` must not abort the caller."""
    result = subprocess.run(
        ["bash", "-c", f"set -euo pipefail; . {LOADER}; echo OK"],
        cwd=REPO_ROOT / "clients",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


@pytest.mark.parametrize("doc", DOCS)
def test_docs_use_the_shared_loader(doc):
    """No doc may carry a hand-rolled env-loading recipe."""
    body = (REPO_ROOT / doc).read_text()
    assert "export $(cat /etc/notifier/.env" not in body
    assert "set -a; . /etc/notifier/.env" not in body
    if "/etc/notifier/.env" in body and "set -a" in body:
        pytest.fail(f"{doc} inlines the env recipe instead of sourcing load_env.sh")
    if "uv run alembic" in body or "uv run pytest" in body:
        assert "load_env.sh" in body, f"{doc} runs env-dependent commands without the loader"


@pytest.mark.parametrize("doc", DOCS)
def test_docs_route_uvicorn_through_the_launch_script(doc):
    """A doc that shows uvicorn must show the guarded launch path (#22).

    Lives here rather than in test_dev_server.py so both doc-surface rules
    share one DOCS list and neither can be dropped without the other.
    """
    body = (REPO_ROOT / doc).read_text()
    if "uvicorn src.api.main:app" in body:
        assert "dev_server.sh" in body
