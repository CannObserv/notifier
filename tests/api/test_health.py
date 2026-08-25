"""Tests for src/api/routes/health.py.

Focus: the build stamp. Both systemd units write it with

    echo BUILD_ID=$(git rev-parse --short HEAD) > /run/notifier/build-id…

and `echo` exits 0 even when the command substitution comes back empty — a
failing `git` is not a failing ExecStartPre. So the app must treat an empty
BUILD_ID exactly like a missing one; `os.environ.get(name, default)` does not,
because the default fires only on absence.
"""

import pytest

from src.api.routes.health import _resolve_build_id


def test_uses_the_stamp_when_one_is_written(monkeypatch):
    monkeypatch.setenv("BUILD_ID", "6c760bf")
    assert _resolve_build_id() == "6c760bf"


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "whitespace"])
def test_falls_back_when_the_stamp_is_blank(monkeypatch, value):
    """A blank stamp reads as a broken health endpoint, not a missing build."""
    monkeypatch.setenv("BUILD_ID", value)
    assert _resolve_build_id() == "dev"


def test_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("BUILD_ID", raising=False)
    assert _resolve_build_id() == "dev"
