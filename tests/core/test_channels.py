"""Tests for src/core/channels.py.

Giving a new consumer the cohort's existing Slack and Mailgun destinations
used to mean reading the Apprise URL from somewhere and pasting it into a
``POST /channels`` — the one step in onboarding that puts a live credential
in an operator's clipboard or an agent's transcript. The API only ever hands
back a masked URL, so there is no API path that avoids it.

The Fernet token is not bound to its tenant (one server key, no associated
data), so the stored ciphertext can be copied as it stands. What is asserted
here is that it is copied *verbatim* — never decrypted and re-encrypted —
that a rehearsal leaves neither rows nor records, and that every refusal
fires before anything is written.
"""

import logging

import pytest
from sqlalchemy import func, select

from src.core.api_keys import TenantNotFoundError
from src.core.channels import (
    ChannelCopy,
    ChannelNameTakenError,
    ChannelNotFoundError,
    SameTenantError,
    copy_channels,
)
from src.core.crypto import decrypt_apprise_url, encrypt_apprise_url
from src.core.logging import AUDIT_LOGGER_NAME
from src.core.models import Channel, Tenant

MISSING = "01J0MISSING000000000000000"
SECRET_URL = "slack://T000/B000/very-secret-token"


def _audit(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == AUDIT_LOGGER_NAME]


async def _channels_of(session, tenant_id) -> list[Channel]:
    result = await session.execute(select(Channel).where(Channel.tenant_id == tenant_id))
    return list(result.scalars())


@pytest.fixture
async def pair(db_session):
    """A source tenant holding one channel, and an empty target tenant."""
    source = Tenant(name="source-tenant")
    target = Tenant(name="target-tenant")
    db_session.add_all([source, target])
    await db_session.flush()
    channel = Channel(
        tenant_id=source.id,
        name="source-slack",
        apprise_url_encrypted=encrypt_apprise_url(SECRET_URL),
        channel_hint="slack",
    )
    db_session.add(channel)
    await db_session.commit()
    return str(source.id), str(target.id), str(channel.id)


class TestCopy:
    async def test_copies_the_ciphertext_verbatim_into_the_target(self, db_session, pair):
        _, target, source_channel = pair
        source_row = await db_session.get(Channel, source_channel)

        copies = await copy_channels(
            db_session, target, [(source_channel, "target-slack")], dry_run=False
        )

        [row] = await _channels_of(db_session, target)
        assert row.apprise_url_encrypted == source_row.apprise_url_encrypted
        assert decrypt_apprise_url(row.apprise_url_encrypted) == SECRET_URL
        assert (row.name, row.channel_hint) == ("target-slack", "slack")
        assert copies == [
            ChannelCopy(
                source_channel_id=source_channel,
                source_tenant_id=pair[0],
                channel_id=str(row.id),
                tenant_id=target,
                name="target-slack",
                channel_hint="slack",
            )
        ]

    async def test_the_source_is_left_alone(self, db_session, pair):
        source, target, source_channel = pair

        await copy_channels(db_session, target, [(source_channel, "target-slack")], dry_run=False)

        [row] = await _channels_of(db_session, source)
        assert (str(row.id), row.name) == (source_channel, "source-slack")

    async def test_the_copy_is_a_new_row_not_a_moved_one(self, db_session, pair):
        _, target, source_channel = pair

        [copy] = await copy_channels(
            db_session, target, [(source_channel, "target-slack")], dry_run=False
        )

        assert copy.channel_id != source_channel

    async def test_several_channels_in_one_run(self, db_session, pair):
        source, target, source_channel = pair
        second = Channel(
            tenant_id=source,
            name="source-mailgun",
            apprise_url_encrypted=encrypt_apprise_url("mailgun://secret"),
            channel_hint="mailgun",
        )
        db_session.add(second)
        await db_session.commit()

        copies = await copy_channels(
            db_session,
            target,
            [(source_channel, "target-slack"), (str(second.id), "target-mailgun")],
            dry_run=False,
        )

        assert [c.name for c in copies] == ["target-slack", "target-mailgun"]
        assert len(await _channels_of(db_session, target)) == 2


class TestRehearsal:
    async def test_dry_run_is_the_default_and_writes_nothing(self, db_session, pair, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        _, target, source_channel = pair

        copies = await copy_channels(db_session, target, [(source_channel, "target-slack")])

        assert [c.name for c in copies] == ["target-slack"]
        assert await _channels_of(db_session, target) == []
        assert _audit(caplog) == []


class TestRecord:
    async def test_one_record_per_copy_naming_both_ends(self, db_session, pair, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        source, target, source_channel = pair

        [copy] = await copy_channels(
            db_session, target, [(source_channel, "target-slack")], dry_run=False
        )

        [record] = _audit(caplog)
        assert record.getMessage() == "channel copied"
        assert (record.source_tenant_id, record.source_channel_id) == (source, source_channel)
        assert (record.tenant_id, record.channel_id) == (target, copy.channel_id)
        assert (record.channel_name, record.channel_hint) == ("target-slack", "slack")

    async def test_the_record_never_carries_the_url(self, db_session, pair, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        _, target, source_channel = pair
        ciphertext = (await db_session.get(Channel, source_channel)).apprise_url_encrypted

        await copy_channels(db_session, target, [(source_channel, "target-slack")], dry_run=False)

        [record] = _audit(caplog)
        rendered = str(vars(record))
        assert SECRET_URL not in rendered
        assert ciphertext not in rendered


class TestRefusals:
    """Every refusal fires before anything is written — rehearsal included."""

    async def _refused(self, db_session, target, exc, copies, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        with pytest.raises(exc):
            await copy_channels(db_session, target, copies, dry_run=False)
        assert _audit(caplog) == []

    async def test_an_unknown_target_tenant(self, db_session, pair, caplog):
        _, _, source_channel = pair
        await self._refused(
            db_session, MISSING, TenantNotFoundError, [(source_channel, "x")], caplog
        )

    async def test_an_unknown_source_channel(self, db_session, pair, caplog):
        _, target, _ = pair
        await self._refused(db_session, target, ChannelNotFoundError, [(MISSING, "x")], caplog)

    async def test_a_copy_into_the_tenant_that_already_owns_it(self, db_session, pair, caplog):
        source, _, source_channel = pair
        await self._refused(db_session, source, SameTenantError, [(source_channel, "x")], caplog)

    async def test_a_name_the_target_already_has(self, db_session, pair, caplog):
        """Names are not unique in the schema, so without this a re-run would
        quietly give the target a second copy of every channel — and a
        consumer whose ``channel_ids`` names one of them would never notice."""
        _, target, source_channel = pair
        await copy_channels(db_session, target, [(source_channel, "target-slack")], dry_run=False)
        caplog.clear()

        await self._refused(
            db_session, target, ChannelNameTakenError, [(source_channel, "target-slack")], caplog
        )
        assert len(await _channels_of(db_session, target)) == 1

    async def test_the_same_name_twice_in_one_request(self, db_session, pair, caplog):
        _, target, source_channel = pair
        await self._refused(
            db_session,
            target,
            ChannelNameTakenError,
            [(source_channel, "dup"), (source_channel, "dup")],
            caplog,
        )

    async def test_a_refusal_part_way_through_writes_none_of_the_run(self, db_session, pair):
        _, target, source_channel = pair

        with pytest.raises(ChannelNotFoundError):
            await copy_channels(
                db_session,
                target,
                [(source_channel, "target-slack"), (MISSING, "second")],
                dry_run=False,
            )

        count = await db_session.execute(
            select(func.count()).select_from(Channel).where(Channel.tenant_id == target)
        )
        assert count.scalar_one() == 0
