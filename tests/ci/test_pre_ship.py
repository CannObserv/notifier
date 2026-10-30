"""Drift tests for scripts/pre-ship.sh — the ship gate's env-loading wrapper.

The shipping skill's Step 1 resolves a project-local ``scripts/pre-ship.sh``
ahead of its own (gregoryfoster/skills#301), so this wrapper is what every
ship runs. It is upstream's "Project-local env loading" recipe with notifier's
``/etc`` path, replacing the forked skill that drifted five times (#153).

Each behavioural test runs a copy in a scratch git repo with a stub delegate
that reports what it inherited, and points ``ETC_ENV`` at a scratch file, so
neither this host's ``/etc/notifier/.env`` nor its absence in CI decides the
result. Stub values are fixtures, never secrets.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "scripts" / "pre-ship.sh"
DELEGATE = "skills/shipping-work-python-fastapi/scripts/pre-ship.sh"
ETC_LINE = 'ETC_ENV="/etc/notifier/.env"'
STUB = """#!/usr/bin/env bash
echo "ARGS=$*"
echo "NAMES=${PRE_SHIP_ENV_NAMES-unset}"
echo "SPACED=${SPACED-unset}"
echo "QUOTED=${QUOTED-unset}"
echo "SHARED=${SHARED-unset}"
exit "${STUB_EXIT:-0}"
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


def _commit(cwd: Path, *args: str) -> None:
    _git(cwd, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", *args)


def _repo(tmp_path: Path, *, delegate: bool = True) -> tuple[Path, Path]:
    """A scratch repo holding the wrapper, and the scratch path standing in for /etc."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    etc_env = tmp_path / "etc.env"
    body = WRAPPER.read_text()
    assert body.count(ETC_LINE) == 1, "the test rewrites this line; keep it literal"
    (root / "scripts" / "pre-ship.sh").write_text(body.replace(ETC_LINE, f'ETC_ENV="{etc_env}"'))
    if delegate:
        stub = root / DELEGATE
        stub.parent.mkdir(parents=True)
        stub.write_text(STUB)
    _git(root, "init", "-q")
    _commit(root, "--allow-empty", "-m", "i")
    return root, etc_env


def _run(cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/pre-ship.sh", *args],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _out(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_wrapper_delegates_through_the_skill_symlink():
    """The symlink is the stable interface; the vendor layout is not."""
    body = WRAPPER.read_text()
    assert f'DELEGATE="{DELEGATE}"' in body
    assert "skills-vendor" not in body
    assert 'exec bash "$DELEGATE" "$@"' in body


def test_wrapper_never_sources_an_env_file():
    body = WRAPPER.read_text()
    assert "set -a" not in body
    assert "| xargs" not in body


def test_missing_delegate_exits_2_naming_the_fix(tmp_path):
    root, _ = _repo(tmp_path, delegate=False)
    result = _run(root)
    assert result.returncode == 2
    assert "git submodule update --init --recursive" in result.stderr


def test_loads_both_files_in_order_and_exports_their_names(tmp_path):
    root, etc_env = _repo(tmp_path)
    etc_env.write_text("# system\nSHARED=etc\nSPACED=two words\n")
    (root / ".env").write_text("export SHARED=repo\nQUOTED=\"a 'b' c\"\nnot a line\n9BAD=x\n")
    result = _run(root)
    assert result.returncode == 0, result.stderr
    out = _out(result)
    assert out["SHARED"] == "repo", "the repo .env overrides /etc's"
    assert out["SPACED"] == "two words"
    assert out["QUOTED"] == "a 'b' c"
    assert out["NAMES"].split() == ["SHARED", "SPACED", "SHARED", "QUOTED"]
    assert "WARN" not in result.stderr


def test_env_file_content_is_never_executed(tmp_path):
    root, etc_env = _repo(tmp_path)
    marker = tmp_path / "ran"
    etc_env.write_text(f"SPACED=$(touch {marker})\ntouch {marker}\n")
    result = _run(root)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert _out(result)["SPACED"] == f"$(touch {marker})"


def test_linked_worktree_falls_back_to_the_primary_env(tmp_path):
    """A gitignored .env lives only in the primary checkout (#110/#129, #147)."""
    root, _ = _repo(tmp_path)
    (root / ".env").write_text("SHARED=primary\n")
    _git(root, "add", "scripts", "skills")
    _commit(root, "-m", "w")
    worktree = tmp_path / "wt"
    _git(root, "worktree", "add", "-q", str(worktree))
    result = _run(worktree)
    assert result.returncode == 0, result.stderr
    assert _out(result)["SHARED"] == "primary"
    assert _out(result)["NAMES"] == "SHARED"


def test_neither_file_warns_and_exports_an_empty_name_list(tmp_path):
    """An empty but exported list is what makes the gate write no stamp (#497)."""
    root, _ = _repo(tmp_path)
    result = _run(root)
    assert result.returncode == 0, result.stderr
    assert "WARN: no env file" in result.stderr
    assert "no stamp is written" in result.stderr
    assert _out(result)["NAMES"] == ""


@pytest.mark.parametrize("code", ["0", "1", "2"])
def test_delegate_exit_code_and_arguments_pass_through(tmp_path, code):
    root, _ = _repo(tmp_path)
    result = _run(root, "--help", STUB_EXIT=code)
    assert result.returncode == int(code)
    assert _out(result)["ARGS"] == "--help"
