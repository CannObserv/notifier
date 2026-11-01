"""Drift tests for scripts/load_env.sh — the one env-loading recipe.

The guarded idiom was 96 characters and appeared nine times across five docs.
That is long enough that people shorten it when copying, and the shortened
form is the unsafe one. One short sourceable line keeps the copyable surface
small and gives these tests a single target.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADER = REPO_ROOT / "scripts" / "load_env.sh"
WRAPPER = REPO_ROOT / "scripts" / "pre-ship.sh"
ETC_LINE = '="/etc/notifier/.env"'
DOCS = [
    "AGENTS.md",
    "README.md",
    "docs/COMMANDS.md",
    "docs/DEPLOYMENT.md",
    "clients/python/README.md",
    # Not prose, and the most-read copy of the recipe there is: it is the
    # error message a developer meets at the moment they need it. It carried
    # the unguarded form until b24f4a0 while this list watched five files
    # that did not.
    "tests/conftest.py",
]


def test_loader_exists():
    assert LOADER.is_file()


def test_loader_is_not_executable():
    """Executing it runs in a subshell where every export is discarded."""
    assert not LOADER.stat().st_mode & stat.S_IXUSR


def test_loader_refuses_to_be_executed():
    """It must fail loudly rather than silently exporting into a subshell."""
    result = subprocess.run(
        ["bash", str(LOADER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "source" in (result.stdout + result.stderr).lower()


def test_loader_never_sources_an_env_file():
    """Sourcing runs a secrets file as shell code; the loader parses it (#154)."""
    body = LOADER.read_text()
    assert "set -a" not in body
    assert "| xargs" not in body
    assert "export $(cat" not in body


def test_loader_lifts_the_parser_from_the_tracked_wrapper():
    """One parser in the repo, pre-ship.sh's, which test_pre_ship holds to upstream.

    Not skills-vendor/: CI's test job and a clone without submodules lack it,
    and dev_server.sh, notifier-dev.service's ExecStart, sources this file.
    """
    body = LOADER.read_text()
    assert "scripts/pre-ship.sh" in body
    assert "skills-vendor" not in body
    assert "read -r line" not in body, "a second copy of the parser"


def _repo(tmp_path: Path, *, wrapper: bool = True) -> tuple[Path, Path]:
    """A scratch repo holding the loader and its parser, and the path standing in for /etc."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    etc_env = tmp_path / "etc.env"
    body = LOADER.read_text()
    assert body.count(ETC_LINE) == 1, "the test rewrites this line; keep it literal"
    (root / "scripts" / "load_env.sh").write_text(body.replace(ETC_LINE, f'="{etc_env}"'))
    if wrapper:
        (root / "scripts" / "pre-ship.sh").write_text(WRAPPER.read_text())
    _git(root, "init", "-q")
    _git(root, "add", "scripts")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "i")
    return root, etc_env


def _git(cwd: Path, *args: str) -> None:
    # GIT_DIR inherited from a hook would point these at the real repo.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(("git", *args), cwd=cwd, env=env, check=True, capture_output=True)


def _source(
    cwd: Path, loader: str = "scripts/load_env.sh", **env: str
) -> subprocess.CompletedProcess[str]:
    """Source the loader under ``set -euo pipefail``, then report what it left behind."""
    report = (
        'echo "SHARED=${SHARED-unset}"; echo "SPACED=${SPACED-unset}"; '
        'echo "QUOTED=${QUOTED-unset}"; echo "NAMES=${PRE_SHIP_ENV_NAMES-unset}"; '
        'echo "EXPORTED=$(env | grep -c ^SHARED=)"; '
        'echo "FUNCS=$(declare -F | grep -c -e load_env -e _notifier)"'
    )
    return subprocess.run(
        ["bash", "-c", f"set -euo pipefail; . {loader}; {report}"],
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "HOME": str(cwd), **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _out(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_loader_loads_both_files_in_order_and_exports_them(tmp_path):
    """/etc first, repo .env over it; spaces and matched quotes survive."""
    root, etc_env = _repo(tmp_path)
    etc_env.write_text("# system\nSHARED=etc\nSPACED=two words\n")
    (root / ".env").write_text("export SHARED=repo\nQUOTED=\"a 'b' c\"\nnot a line\n9BAD=x\n")
    result = _source(root)
    assert result.returncode == 0, result.stderr
    out = _out(result)
    assert out["SHARED"] == "repo", "the repo .env overrides /etc's"
    assert out["SPACED"] == "two words"
    assert out["QUOTED"] == "a 'b' c"
    assert out["EXPORTED"] == "1", "loaded values reach child processes"


def test_loader_never_executes_env_file_content(tmp_path):
    """A ``$(...)`` value stays literal, and a bare command line is skipped."""
    root, etc_env = _repo(tmp_path)
    marker = tmp_path / "ran"
    etc_env.write_text(f"SPACED=$(touch {marker})\ntouch {marker}\n")
    result = _source(root)
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert _out(result)["SPACED"] == f"$(touch {marker})"


def test_loader_leaves_the_callers_shell_clean(tmp_path):
    """No helper functions left behind, and a ship run's stamp list untouched.

    The lifted parser appends every name to PRE_SHIP_ENV_NAMES, which keys the
    ship gate's pass stamp; a loader sourced under that gate must not edit it.
    """
    root, etc_env = _repo(tmp_path)
    etc_env.write_text("SHARED=etc\n")
    result = _source(root, PRE_SHIP_ENV_NAMES="ALREADY")
    assert result.returncode == 0, result.stderr
    assert _out(result)["NAMES"] == "ALREADY"
    assert _out(result)["FUNCS"] == "0"
    assert _out(_source(root))["NAMES"] == "unset"


def test_loader_in_a_linked_worktree_reads_the_primary_env(tmp_path):
    """A git-ignored .env lives only in the primary checkout."""
    root, _ = _repo(tmp_path)
    (root / ".env").write_text("SHARED=primary\n")
    worktree = tmp_path / "wt"
    _git(root, "worktree", "add", "-q", str(worktree))
    result = _source(worktree)
    assert result.returncode == 0, result.stderr
    assert _out(result)["SHARED"] == "primary"


def test_loader_outside_git_loads_only_what_it_finds(tmp_path):
    """No repo to ask (an exported tarball): the fallback must not guess a path."""
    root, etc_env = _repo(tmp_path)
    etc_env.write_text("SHARED=etc\n")
    subprocess.run(["rm", "-rf", str(root / ".git")], check=True)
    (tmp_path / ".env").write_text("SHARED=wrong\n")  # the caller's cwd, not the repo's
    result = _source(tmp_path, loader=str(root / "scripts" / "load_env.sh"))
    assert result.returncode == 0, result.stderr
    assert _out(result)["SHARED"] == "etc"


def test_loader_without_its_parser_fails_loudly(tmp_path):
    """A missing or renamed parser must not load nothing and report success."""
    root, etc_env = _repo(tmp_path, wrapper=False)
    etc_env.write_text("SHARED=etc\n")
    result = _source(root)
    assert result.returncode != 0
    assert "pre-ship.sh" in result.stderr


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
