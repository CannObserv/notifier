"""Tests for scripts/copy_channels.py.

The core copy is tested in ``tests/core/test_channels.py``. What is asserted
here is what the script adds: parsing ``SOURCE_ID=NEW_NAME`` pairs, the
``--expect-name`` guard, and output an operator can act on. The guard is
required, not optional: the target id is the whole of who receives the grant,
and a typo that names another consumer would hand *that* consumer the cohort's
Slack and mail recipients.
"""

import secrets

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import scripts.copy_channels as copy_channels_module
from scripts.copy_channels import OK, REFUSED, main, parse_args
from src.core.crypto import encrypt_apprise_url
from src.core.models import Channel, Tenant

SOURCE = "01J0SOURCE0000000000000000"
TARGET = "01J0TARGET0000000000000000"


@pytest.fixture
async def live_session(test_engine):
    """A session that really commits; the script owns its transaction."""
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
async def live_pair(live_session):
    """A committed source tenant with one channel, and an empty target.

    Yields ``(source_channel_id, target_id, target_name)`` and removes both
    tenants afterwards; the cascade takes their channels.
    """
    source = Tenant(name=f"src-{secrets.token_hex(4)}")
    target = Tenant(name=f"dst-{secrets.token_hex(4)}")
    live_session.add_all([source, target])
    await live_session.flush()
    channel = Channel(
        tenant_id=source.id,
        name="source-slack",
        apprise_url_encrypted=encrypt_apprise_url("slack://secret"),
        channel_hint="slack",
    )
    live_session.add(channel)
    await live_session.commit()
    # Strings, captured now: after a rollback the ORM attributes are expired
    # and reading them is a lazy load outside the greenlet.
    tenant_ids = [str(source.id), str(target.id)]
    yield str(channel.id), tenant_ids[1], target.name
    await live_session.rollback()
    await live_session.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
    await live_session.commit()


@pytest.fixture
def factory(monkeypatch, test_engine):
    """Point ``main`` at the test database."""
    monkeypatch.setattr(
        copy_channels_module,
        "get_session_factory",
        lambda: async_sessionmaker(test_engine, expire_on_commit=False),
    )


async def _target_channels(session, target_id) -> list[str]:
    result = await session.execute(select(Channel.name).where(Channel.tenant_id == target_id))
    return sorted(result.scalars())


class TestArgumentParsing:
    def test_a_full_command_line(self):
        args = parse_args(
            ["--to-tenant", TARGET, "--expect-name", "acme", "--channel", f"{SOURCE}=acme-slack"]
        )

        assert args.to_tenant == TARGET
        assert args.expect_name == "acme"
        assert args.channel == [(SOURCE, "acme-slack")]
        assert args.dry_run is False

    def test_channel_repeats(self):
        args = parse_args(
            [
                "--to-tenant",
                TARGET,
                "--expect-name",
                "acme",
                "--channel",
                f"{SOURCE}=a",
                "--channel",
                f"{SOURCE}=b",
            ]
        )

        assert [name for _, name in args.channel] == ["a", "b"]

    @pytest.mark.parametrize("spec", ["no-equals", "=name", f"{SOURCE}=", f"{SOURCE}= "])
    def test_a_malformed_channel_spec(self, spec):
        with pytest.raises(SystemExit):
            parse_args(["--to-tenant", TARGET, "--expect-name", "a", "--channel", spec])

    def test_the_expected_name_is_required(self):
        with pytest.raises(SystemExit):
            parse_args(["--to-tenant", TARGET, "--channel", f"{SOURCE}=a"])

    def test_at_least_one_channel(self):
        with pytest.raises(SystemExit):
            parse_args(["--to-tenant", TARGET, "--expect-name", "a"])


class TestMain:
    async def test_a_real_run_copies_and_prints_the_new_ids(
        self, factory, live_session, live_pair, capsys
    ):
        source_channel, target, target_name = live_pair
        args = parse_args(
            [
                "--to-tenant",
                target,
                "--expect-name",
                target_name,
                "--channel",
                f"{source_channel}=dst-slack",
            ]
        )

        assert await main(args) == OK

        assert await _target_channels(live_session, target) == ["dst-slack"]
        out = capsys.readouterr().out
        assert "channel_id=" in out
        assert "name=dst-slack" in out
        assert f"source_channel_id={source_channel}" in out
        assert "slack://" not in out

    async def test_a_rehearsal_writes_nothing(self, factory, live_session, live_pair, capsys):
        source_channel, target, target_name = live_pair
        args = parse_args(
            [
                "--to-tenant",
                target,
                "--expect-name",
                target_name,
                "--channel",
                f"{source_channel}=dst-slack",
                "--dry-run",
            ]
        )

        assert await main(args) == OK

        assert await _target_channels(live_session, target) == []
        assert capsys.readouterr().out.startswith("DRY RUN")

    async def test_a_name_mismatch_is_refused_before_anything_is_written(
        self, factory, live_session, live_pair, capsys
    ):
        source_channel, target, _ = live_pair
        args = parse_args(
            [
                "--to-tenant",
                target,
                "--expect-name",
                "somebody-else",
                "--channel",
                f"{source_channel}=dst-slack",
            ]
        )

        assert await main(args) == REFUSED

        assert await _target_channels(live_session, target) == []
        assert "somebody-else" in capsys.readouterr().err

    async def test_a_core_refusal_is_reported_not_raised(
        self, factory, live_session, live_pair, capsys
    ):
        _, target, target_name = live_pair
        args = parse_args(
            [
                "--to-tenant",
                target,
                "--expect-name",
                target_name,
                "--channel",
                "01J0MISSING000000000000000=x",
            ]
        )

        assert await main(args) == REFUSED
        assert "Nothing was written." in capsys.readouterr().err
