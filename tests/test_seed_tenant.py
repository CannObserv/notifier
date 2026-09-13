"""Tests for scripts/seed_tenant.py.

Mostly about its *output*, which is an interface with two consumers: an
operator copying a line into a consumer's secrets, and
``clients/python/tests/conftest.py``, which shells this script and parses
stdout with `tenant_id=(\\S+)` / `raw_key=(\\S+)`. Nothing failed loudly when
that shape drifted — the SDK's integration fixture just stopped being able to
seed, one layer away from the change that broke it.
"""

import re

import pytest
from sqlalchemy import select

from scripts.seed_tenant import main
from src.core.api_keys import hash_key
from src.core.models import ApiKey, Tenant

#: Transcribed from clients/python/tests/conftest.py. A copy, deliberately:
#: the point is to fail here when seed_tenant's output stops satisfying them.
SDK_TENANT_PATTERN = re.compile(r"tenant_id=(\S+)")
SDK_KEY_PATTERN = re.compile(r"raw_key=(\S+)")


@pytest.fixture
def seeded(capsys, monkeypatch, test_engine):
    """Run ``main`` against the test database and return its parsed output."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import scripts.seed_tenant as module

    monkeypatch.setattr(
        module,
        "get_session_factory",
        lambda: async_sessionmaker(test_engine, expire_on_commit=False),
    )
    return capsys


class TestOutput:
    async def test_prints_what_the_sdk_fixture_parses(self, seeded):
        await main("seed-output-tenant", "smoke", "production")

        out = seeded.readouterr().out
        assert SDK_TENANT_PATTERN.search(out), out
        assert SDK_KEY_PATTERN.search(out), out

    async def test_prints_the_key_id(self, seeded):
        """rotate_key.py --revoke takes a key id. Minting one without ever
        printing it is what sends the next operator to ad-hoc SQL to find it
        (#62)."""
        await main("seed-key-id-tenant", "smoke", "production")

        assert re.search(r"key_id=(\S+)", seeded.readouterr().out)

    async def test_shows_the_raw_key_exactly_once(self, seeded):
        out_before = seeded.readouterr().out  # drain
        assert out_before is not None
        await main("seed-once-tenant", "smoke", "production")

        out = seeded.readouterr().out
        raw = SDK_KEY_PATTERN.search(out).group(1)
        assert out.count(raw) == 1


class TestPersistence:
    async def test_stores_only_the_hash(self, seeded, db_session):
        await main("seed-hash-tenant", "smoke", "production")
        raw = SDK_KEY_PATTERN.search(seeded.readouterr().out).group(1)

        row = (
            (await db_session.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(raw))))
            .scalars()
            .one()
        )
        assert raw not in (row.key_prefix + row.label + row.key_hash)

    async def test_creates_a_new_tenant_every_time(self, seeded, db_session):
        """It only ever creates. Attaching a key to a tenant that already
        exists is rotate_key.py's job, and keeping the two apart is why a
        script named seed_tenant never deletes a credential."""
        await main("seed-new-tenant-a", "smoke", "production")
        await main("seed-new-tenant-b", "smoke", "production")

        names = (
            (
                await db_session.execute(
                    select(Tenant.name).where(Tenant.name.like("seed-new-tenant-%"))
                )
            )
            .scalars()
            .all()
        )
        assert sorted(names) == ["seed-new-tenant-a", "seed-new-tenant-b"]
