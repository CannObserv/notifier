"""Tests for src/api/routes/health.py.

Focus: the build stamp. Both systemd units write it with

    echo BUILD_ID=$(git rev-parse --short HEAD) > /run/notifier/build-id…

and `echo` exits 0 even when the command substitution comes back empty — a
failing `git` is not a failing ExecStartPre. So the app must treat an empty
BUILD_ID exactly like a missing one; `os.environ.get(name, default)` does not,
because the default fires only on absence.
"""

import os

import pytest

from src.api.routes.health import _resolve_build_id, _resolve_database
from src.core.db_safety import database_name


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


def test_names_the_database_and_classifies_it(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/notifier_dev")
    assert _resolve_database() == ("notifier_dev", "development")


def test_classifies_production_by_the_absence_of_a_suffix(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/notifier")
    assert _resolve_database() == ("notifier", "production")


def test_a_third_database_is_named_even_though_it_classifies_as_production(monkeypatch):
    """The name is what makes a misconfiguration visible.

    ``serving_production()`` collapses every non-suffixed name onto
    ``production`` — correct, and it is why the classification alone cannot
    tell ``notifier`` from ``notifier_staging``.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/notifier_staging")
    assert _resolve_database() == ("notifier_staging", "production")


@pytest.mark.parametrize(
    "url", ["", "notifier", "postgresql+asyncpg://h/"], ids=["unset", "no-scheme", "no-name"]
)
def test_an_unreadable_url_fails_soft_to_unknown_production(monkeypatch, url):
    """Unlike the guard, this must not take liveness down.

    ``database_name()`` raises on any URL it cannot read. Letting that escape
    at import time means the app never starts, which is worse than the bug
    being fixed — so report ``unknown`` and, following ``serving_production()``,
    the conservative ``production``.
    """
    monkeypatch.setenv("DATABASE_URL", url)
    assert _resolve_database() == ("unknown", "production")


@pytest.mark.asyncio
async def test_health_payload_carries_the_endpoint_identity(client):
    """`build` agrees across both ports by design; `environment` is the signal."""
    body = (await client.get("/health")).json()
    assert set(body) == {"status", "build", "database", "environment"}


@pytest.mark.asyncio
async def test_ready_reports_the_database_actually_connected(client):
    """Ground truth: ``current_database()``, not what DATABASE_URL claims."""
    body = (await client.get("/ready")).json()
    assert body["database"] == database_name(os.environ["TEST_DATABASE_URL"])
    assert body["environment"] == "development"


@pytest.mark.asyncio
async def test_the_two_probes_agree_on_which_database_this_is(client):
    """The assertion a consumer's wiring-up check ultimately rests on.

    Asserting only that ``environment`` is one of its two legal values passes
    for either, so a ``/health`` claiming ``production`` while serving
    ``notifier_test`` would be green — the exact failure #58 exists to make
    impossible. Agreement is the stronger claim, and it needs no literal
    database name: ``/health`` reads the configured URL and ``/ready`` reads
    the live connection, so the two matching is what says those have not
    diverged.
    """
    health = (await client.get("/health")).json()
    ready = (await client.get("/ready")).json()
    assert (health["database"], health["environment"]) == (
        ready["database"],
        ready["environment"],
    )
