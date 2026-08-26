"""Tests for scripts/seed_dev_channels.py.

The dev tenant had a working key and nothing to dispatch to (#26), so watcher
could authenticate and construct a client but never exercise the notification
path end to end. These sinks close that gap, and the script that creates them
has to be safe to re-run and impossible to point at production.
"""

import pytest
from sqlalchemy import select

from scripts.seed_dev_channels import DEV_SINKS, WrongDatabaseError, assert_dev_database, seed
from src.core.crypto import decrypt_apprise_url
from src.core.models import Channel


class TestDatabaseGuard:
    """Stricter than src.core.db_safety on purpose.

    That guard permits any `_test` or `_dev` name, and lets
    NOTIFIER_ALLOW_PROD_DB open production deliberately. Seeding fixture rows
    is never a deliberate production operation, so this one accepts `_dev`
    alone and has no escape hatch.
    """

    def test_accepts_a_dev_database(self):
        assert_dev_database("postgresql+asyncpg://u@h/notifier_dev") is None

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql+asyncpg://u@h/notifier",
            "postgresql+asyncpg://u@h/notifier_test",
            "postgresql+asyncpg://u@h/notifier_dev_backup",
        ],
        ids=["production", "test", "suffix-lookalike"],
    )
    def test_refuses_anything_else(self, url):
        with pytest.raises(WrongDatabaseError):
            assert_dev_database(url)

    def test_the_production_opt_in_does_not_apply(self, monkeypatch):
        """NOTIFIER_ALLOW_PROD_DB opens production for migrations and the live
        service. It must not open it for fixture rows."""
        monkeypatch.setenv("NOTIFIER_ALLOW_PROD_DB", "1")
        with pytest.raises(WrongDatabaseError):
            assert_dev_database("postgresql+asyncpg://u@h/notifier")


class TestSinkDefinitions:
    def test_one_sink_succeeds_and_one_fails(self):
        """Watcher needs both: a delivery that lands, and a failure it can
        handle, neither of which reaches a real subscriber."""
        assert {s.expected_outcome for s in DEV_SINKS} == {"succeeds", "fails"}

    def test_no_sink_can_reach_a_real_recipient(self):
        """syslog goes to this VM's journal; the failing one is a port
        nothing binds. Neither leaves the host."""
        for sink in DEV_SINKS:
            assert sink.apprise_url.startswith(("syslog://", "json://127.0.0.1:"))


class TestSeeding:
    async def test_creates_the_sinks(self, db_session, tenant):
        created = await seed(db_session, tenant.id)

        assert len(created) == len(DEV_SINKS)
        rows = (
            (await db_session.execute(select(Channel).where(Channel.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        assert {r.name for r in rows} == {s.name for s in DEV_SINKS}

    async def test_urls_are_encrypted_at_rest(self, db_session, tenant):
        await seed(db_session, tenant.id)
        row = (
            (await db_session.execute(select(Channel).where(Channel.tenant_id == tenant.id)))
            .scalars()
            .first()
        )
        assert "syslog" not in row.apprise_url_encrypted
        assert decrypt_apprise_url(row.apprise_url_encrypted).startswith(("syslog://", "json://"))

    async def test_is_safe_to_rerun(self, db_session, tenant):
        """Re-running must not duplicate rows — watcher would then see two
        channels where the docs promise one."""
        await seed(db_session, tenant.id)
        second = await seed(db_session, tenant.id)

        assert second == []
        rows = (
            (await db_session.execute(select(Channel).where(Channel.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        assert len(rows) == len(DEV_SINKS)
