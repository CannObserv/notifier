"""Tests for src/core/api_keys.py.

The minting half existed only inside ``scripts/seed_tenant.py``, where
``[tool.coverage.run] source = ["src"]`` cannot see it — credential logic was
the one part of this service the 80% gate never measured (#62). Moving it here
buys the gate, one spelling of the hash the auth path already computes, and a
revoke path that can be tested without a subprocess.
"""

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.api_keys import (
    RAW_KEY_PREFIX,
    KeyNotFoundError,
    KeyOwnershipError,
    LastKeyError,
    SavepointError,
    TenantNotFoundError,
    generate_raw_key,
    hash_key,
    key_count,
    keys_for,
    mint,
    record_audit,
    revoke,
    ulid_str,
)
from src.core.db_safety import database_name
from src.core.logging import AUDIT_LOGGER_NAME
from src.core.models import ApiKey, Tenant

#: What every record from the suite's own sessions must name (#101).
TEST_DATABASE = database_name(os.environ["TEST_DATABASE_URL"])


def _audit(caplog) -> list[logging.LogRecord]:
    """The audit records captured so far, and nothing else."""
    return [r for r in caplog.records if r.name == AUDIT_LOGGER_NAME]


async def _count(session, tenant_id: str) -> int:
    result = await session.execute(
        select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


class TestHashKey:
    def test_matches_the_spelling_the_auth_path_uses(self):
        """src/api/deps.py looks a key up by this digest. A second spelling
        here would be a credential that mints but cannot authenticate."""
        raw = "nk_whatever"
        assert hash_key(raw) == hashlib.sha256(raw.encode()).hexdigest()

    def test_is_deterministic(self):
        assert hash_key("nk_abc") == hash_key("nk_abc")

    def test_distinct_keys_hash_distinctly(self):
        assert hash_key("nk_abc") != hash_key("nk_abd")


class TestGenerateRawKey:
    def test_carries_the_recognisable_prefix(self):
        assert generate_raw_key().startswith(RAW_KEY_PREFIX)

    def test_every_call_differs(self):
        assert len({generate_raw_key() for _ in range(50)}) == 50

    def test_carries_at_least_256_bits_of_entropy(self):
        """token_urlsafe(32) is 32 random bytes; base64 renders them in 43
        characters. A shorter key would be a silent downgrade."""
        assert len(generate_raw_key()) >= len(RAW_KEY_PREFIX) + 43


class TestMint:
    async def test_persists_a_key_for_the_tenant(self, db_session, tenant):
        key, _raw = await mint(db_session, tenant.id, "label-a", "production")

        assert key.tenant_id == tenant.id
        assert key.label == "label-a"
        assert key.environment == "production"
        assert await _count(db_session, tenant.id) == 1

    async def test_returns_a_raw_key_that_authenticates(self, db_session, tenant):
        key, raw = await mint(db_session, tenant.id, "label-a", "production")

        assert key.key_hash == hash_key(raw)
        assert key.key_prefix == raw[:8]

    async def test_never_persists_the_raw_key(self, db_session, tenant):
        """Only the digest is stored. A raw key recoverable from the row would
        make the database a credential store rather than a verifier."""
        _key, raw = await mint(db_session, tenant.id, "label-a", "production")

        row = (
            (await db_session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id)))
            .scalars()
            .one()
        )
        stored = (row.label, row.key_prefix, row.key_hash, row.environment)
        assert not any(raw in field for field in stored)

    async def test_mints_a_development_key(self, db_session, tenant):
        key, _raw = await mint(db_session, tenant.id, "label-a", "development")

        assert key.environment == "development"

    async def test_refuses_an_unknown_environment(self, db_session, tenant):
        """The model's CheckConstraint would catch this at flush with a
        database error naming a constraint. Refuse it by name instead."""
        with pytest.raises(ValueError, match="staging"):
            await mint(db_session, tenant.id, "label-a", "staging")
        assert await _count(db_session, tenant.id) == 0

    async def test_refuses_an_unknown_tenant(self, db_session):
        """The foreign key would raise at flush. This names the tenant id the
        operator actually typed."""
        with pytest.raises(TenantNotFoundError, match="01BOGUSTENANTID0000000000"):
            await mint(db_session, "01BOGUSTENANTID0000000000", "label-a", "production")

    async def test_a_second_key_joins_the_first(self, db_session, tenant):
        """The gap #62 opens with: seed_tenant.py could only ever create a
        tenant, so a consumer needing two credentials had no path."""
        await mint(db_session, tenant.id, "label-a", "production")
        await mint(db_session, tenant.id, "label-b", "production")

        assert await _count(db_session, tenant.id) == 2

    async def test_does_not_commit(self, db_session, tenant):
        """The caller owns the transaction, which is what lets a rotation put
        the mint and the revoke in one."""
        await mint(db_session, tenant.id, "label-a", "production")
        await db_session.rollback()

        assert await _count(db_session, tenant.id) == 0


class TestKeyCount:
    async def test_counts_only_this_tenant(self, db_session, tenant):
        other = Tenant(name="other-tenant-for-count")
        db_session.add(other)
        await db_session.flush()
        await mint(db_session, tenant.id, "label-a", "production")
        await mint(db_session, other.id, "label-b", "production")
        await mint(db_session, other.id, "label-c", "production")

        assert await key_count(db_session, tenant.id) == 1
        assert await key_count(db_session, other.id) == 2


class TestRevoke:
    async def test_removes_the_row(self, db_session, tenant):
        doomed, _ = await mint(db_session, tenant.id, "old", "production")
        await mint(db_session, tenant.id, "new", "production")

        await revoke(db_session, tenant.id, doomed.id)

        remaining = (
            (await db_session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        assert [r.label for r in remaining] == ["new"]

    async def test_returns_a_snapshot_of_what_it_deleted(self, db_session, tenant):
        """The operator has to be able to read back which key just died —
        the confirmation the ad-hoc #57 rotation had no way to print."""
        doomed, raw = await mint(db_session, tenant.id, "old", "production")
        doomed.last_used_at = datetime(2026, 9, 12, 4, 30, tzinfo=UTC)
        await mint(db_session, tenant.id, "new", "production")

        snapshot = await revoke(db_session, tenant.id, doomed.id)

        assert snapshot.label == "old"
        assert snapshot.key_prefix == raw[:8]
        assert snapshot.environment == "production"
        assert snapshot.last_used_at == datetime(2026, 9, 12, 4, 30, tzinfo=UTC)

    async def test_refuses_an_unknown_key(self, db_session, tenant):
        await mint(db_session, tenant.id, "a", "production")
        await mint(db_session, tenant.id, "b", "production")

        with pytest.raises(KeyNotFoundError, match="01BOGUSKEYID000000000000"):
            await revoke(db_session, tenant.id, "01BOGUSKEYID000000000000")
        assert await _count(db_session, tenant.id) == 2

    async def test_refuses_a_key_belonging_to_another_tenant(self, db_session, tenant):
        """One mistyped ULID must not be able to revoke a different
        consumer's credential."""
        victim = Tenant(name="innocent-bystander")
        db_session.add(victim)
        await db_session.flush()
        theirs, _ = await mint(db_session, victim.id, "theirs", "production")
        await mint(db_session, victim.id, "theirs-2", "production")

        with pytest.raises(KeyOwnershipError) as exc:
            await revoke(db_session, tenant.id, theirs.id)

        assert str(victim.id) in str(exc.value)
        assert str(tenant.id) in str(exc.value)
        assert await _count(db_session, victim.id) == 2

    async def test_refuses_the_tenants_last_key(self, db_session, tenant):
        """A tenant with zero keys is a consumer that is down, and nothing
        says why."""
        only, _ = await mint(db_session, tenant.id, "only", "production")

        with pytest.raises(LastKeyError, match="last"):
            await revoke(db_session, tenant.id, only.id)
        assert await _count(db_session, tenant.id) == 1

    async def test_allow_last_overrides_the_refusal(self, db_session, tenant):
        only, _ = await mint(db_session, tenant.id, "only", "production")

        await revoke(db_session, tenant.id, only.id, allow_last=True)

        assert await _count(db_session, tenant.id) == 0

    async def test_a_freshly_minted_replacement_makes_the_old_key_not_the_last(
        self, db_session, tenant
    ):
        """The last-key guard must not fire on a rotation. Mint flushes before
        revoke counts, so the tenant is never at zero and --force is never
        reachable on this path."""
        old, _ = await mint(db_session, tenant.id, "old", "production")
        await mint(db_session, tenant.id, "new", "production")

        await revoke(db_session, tenant.id, old.id)

        assert await _count(db_session, tenant.id) == 1

    async def test_accepts_a_tenant_id_as_a_plain_string(self, db_session, tenant):
        """An operator's argv holds a str; the row holds a ulid.ULID. A
        tenancy check that leaned on those comparing equal would refuse every
        revoke the day that stopped being true."""
        old, _ = await mint(db_session, tenant.id, "old", "production")
        await mint(db_session, tenant.id, "new", "production")

        snapshot = await revoke(db_session, str(tenant.id), str(old.id))

        assert snapshot.label == "old"

    async def test_the_ownership_message_renders_bare_ulids(self, db_session, tenant):
        """`ULID(01J...)` in an incident message is one more thing for a tired
        operator to misread against the id they typed."""
        victim = Tenant(name="bystander-for-message")
        db_session.add(victim)
        await db_session.flush()
        theirs, _ = await mint(db_session, victim.id, "theirs", "production")
        await mint(db_session, victim.id, "theirs-2", "production")

        with pytest.raises(KeyOwnershipError) as exc:
            await revoke(db_session, tenant.id, theirs.id)

        assert "ULID(" not in str(exc.value)


class TestRotationAtomicity:
    async def test_an_abandoned_rotation_leaves_the_original_key_intact(self, db_session, tenant):
        """Neither mint nor revoke commits, so a rotation that dies partway
        through cannot leave a tenant holding a key nobody has. This is the
        whole reason the two halves share a transaction.

        The rotation is the session's own transaction, not a savepoint: a
        mint or revoke inside one is refused (#100)."""
        original, original_raw = await mint(db_session, tenant.id, "original", "production")
        original_id = str(original.id)
        tenant_id = str(tenant.id)
        await db_session.commit()

        await mint(db_session, tenant_id, "replacement", "production")
        await revoke(db_session, tenant_id, original_id)
        await db_session.rollback()

        surviving = (
            (await db_session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant_id)))
            .scalars()
            .all()
        )
        assert [r.label for r in surviving] == ["original"]
        assert surviving[0].key_hash == hash_key(original_raw)


class TestUlidStr:
    def test_renders_a_ulid_without_its_wrapper(self, tenant):
        assert ulid_str(tenant.id) == str(tenant.id)
        assert "ULID(" not in ulid_str(tenant.id)

    def test_passes_a_string_through(self):
        assert ulid_str("01J0000000000000000000000") == "01J0000000000000000000000"


class TestKeysFor:
    async def test_lists_this_tenants_keys_oldest_first(self, db_session, tenant):
        """The operator needs the key *id* to revoke one, and until this
        existed there was no sanctioned way to read it — which sends them
        back to the ad-hoc SQL #62 is trying to retire."""
        await mint(db_session, tenant.id, "first", "production")
        await mint(db_session, tenant.id, "second", "development")

        records = await keys_for(db_session, tenant.id)

        assert [r.label for r in records] == ["first", "second"]
        assert [r.environment for r in records] == ["production", "development"]

    async def test_excludes_other_tenants(self, db_session, tenant):
        other = Tenant(name="other-tenant-for-listing")
        db_session.add(other)
        await db_session.flush()
        await mint(db_session, tenant.id, "mine", "production")
        await mint(db_session, other.id, "theirs", "production")

        assert [r.label for r in await keys_for(db_session, tenant.id)] == ["mine"]

    async def test_renders_bare_ulids(self, db_session, tenant):
        await mint(db_session, tenant.id, "first", "production")

        record = (await keys_for(db_session, tenant.id))[0]

        assert "ULID(" not in record.id
        assert "ULID(" not in record.tenant_id

    async def test_refuses_an_unknown_tenant(self, db_session):
        """An empty list for a mistyped id reads identically to a tenant that
        genuinely holds no keys — the difference between a typo and a consumer
        that is already down."""
        with pytest.raises(TenantNotFoundError):
            await keys_for(db_session, "01BOGUSTENANTID0000000000")


class TestLastKeyCheckIsSerialized:
    async def test_revoke_locks_the_tenant_row(self, db_session, tenant):
        """Two concurrent revokes could each read a count of 2 and each
        delete, landing the tenant at zero keys — the outcome the guard
        exists to prevent and that --force exists to make deliberate.
        Locking the tenant row makes the second wait for the first's
        commit, so it counts 1 and refuses (CR 7).
        """
        await mint(db_session, tenant.id, "a", "production")
        await mint(db_session, tenant.id, "b", "production")

        statements = []

        @event.listens_for(db_session.sync_session, "do_orm_execute")
        def record(orm_context):
            statements.append(str(orm_context.statement).lower())

        key_b = (
            (await db_session.execute(select(ApiKey).where(ApiKey.label == "b"))).scalars().one()
        )
        await revoke(db_session, tenant.id, key_b.id)

        event.remove(db_session.sync_session, "do_orm_execute", record)
        assert any("for update" in s and "tenants" in s for s in statements), statements

    async def test_force_takes_no_lock(self, db_session, tenant):
        """Under allow_last the delete is unconditional: no count is read, so
        there is no read-then-write to serialize. A lock that protects nothing
        invites the next reader to assume it protects something (CR 16)."""
        only, _ = await mint(db_session, tenant.id, "only", "production")

        statements = []

        @event.listens_for(db_session.sync_session, "do_orm_execute")
        def record(orm_context):
            statements.append(str(orm_context.statement).lower())

        await revoke(db_session, tenant.id, only.id, allow_last=True)

        event.remove(db_session.sync_session, "do_orm_execute", record)
        assert not any("for update" in s for s in statements), statements


class TestAuditRecords:
    """Every mint and every revoke names the key, on the audit channel (#67).

    #62 declined a `revoked_at` column — DELETE fails closed where a filter
    everyone must remember fails open — and paid for the lost audit trail with
    a log line here. The line existed and had never once been emitted: it went
    to `src.core.api_keys`, whose records the two credential scripts dropped on
    the floor. A revoke left nothing at all, the row and its going both gone.

    Asserting on the logger *name* as well as the payload: routing these back
    through the module logger renders identically today and silently leaves the
    journal again the moment an entry point configures only the root.
    """

    async def test_mint_records_the_key_it_made(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

        key, _ = await mint(db_session, tenant.id, "nightly backup", "development")
        await db_session.commit()

        (record,) = _audit(caplog)
        assert record.message == "api key minted"
        assert record.tenant_id == str(tenant.id)
        assert record.key_id == str(key.id)
        assert record.key_prefix == key.key_prefix
        assert record.label == "nightly backup"
        assert record.environment == "development"
        assert record.database == TEST_DATABASE

    async def test_mint_never_records_the_raw_key(self, db_session, tenant, caplog):
        """The prefix identifies the key to a human; the secret is the one
        thing a durable record must never hold."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

        _, raw = await mint(db_session, tenant.id, "smoke", "production")
        await db_session.commit()

        (record,) = _audit(caplog)
        assert raw not in json.dumps(record.__dict__, default=str)

    async def test_revoke_records_what_went(self, db_session, tenant, caplog):
        """The row is gone after this; the record is all there is."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        key, _ = await mint(db_session, tenant.id, "doomed", "production")
        await mint(db_session, tenant.id, "survivor", "production")
        await db_session.commit()
        caplog.clear()  # the setup's own mints are not what this asserts on

        await revoke(db_session, tenant.id, key.id)
        await db_session.commit()

        (record,) = _audit(caplog)
        assert record.message == "api key revoked"
        assert record.tenant_id == str(tenant.id)
        assert record.key_id == str(key.id)
        assert record.key_prefix == key.key_prefix
        assert record.label == "doomed"
        assert record.environment == "production"
        assert record.database == TEST_DATABASE

    async def test_a_refused_revoke_records_nothing(self, db_session, tenant, caplog):
        """The last-key guard writes nothing, so it must claim nothing."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        key, _ = await mint(db_session, tenant.id, "only", "production")
        await db_session.commit()
        caplog.clear()

        with pytest.raises(LastKeyError):
            await revoke(db_session, tenant.id, key.id)
        await db_session.commit()

        assert _audit(caplog) == []


class TestRecordAudit:
    """Every record names the database it came from (#101).

    `environment` cannot: it is how the *key* is marked, and a `production`
    key can be minted into `notifier_dev`. Without this a dev rotation reads
    as a production credential change, and the only way to tell them apart is
    looking the key up in both databases — which a revoke's DELETE forecloses.

    An engine that never connects: the name comes from the session's bind,
    so these need no dev database and touch none.
    """

    DEV_URL = "postgresql+asyncpg://notifier:hunter2@db.invalid/notifier_dev"

    async def _recorded(self, caplog, **fields: str) -> logging.LogRecord:
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        engine = create_async_engine(self.DEV_URL)
        try:
            async with AsyncSession(engine) as session:
                record_audit(session, "api key minted", {"key_id": "01J0KEY", **fields})
        finally:
            await engine.dispose()
        (record,) = _audit(caplog)
        return record

    async def test_a_dev_database_record_says_so(self, caplog):
        record = await self._recorded(caplog)
        assert (record.message, record.key_id) == ("api key minted", "01J0KEY")
        assert record.database == "notifier_dev"

    async def test_names_the_database_and_never_the_url(self, caplog):
        """The URL carries the password; the name is all the record needs."""
        payload = json.dumps((await self._recorded(caplog)).__dict__, default=str)
        assert "hunter2" not in payload
        assert "db.invalid" not in payload

    async def test_a_field_cannot_mislabel_the_database(self, caplog):
        """The bind is the fact; a caller's field of the same name is not."""
        record = await self._recorded(caplog, database="notifier")
        assert record.database == "notifier_dev"

    def test_is_the_only_way_onto_the_channel(self):
        """A module that reaches the audit logger directly emits records with
        no ``database``, and every test above still passes (CR 2). Equality,
        not a subset: a scan that reads nothing must fail too, not pass."""
        root = Path(__file__).parent.parent.parent
        reach = re.compile(r"get_audit_logger|AUDIT_LOGGER_NAME|[\"']notifier\.audit[\"']")
        reaching = {
            str(path.relative_to(root))
            for tree in ("src", "scripts")
            for path in (root / tree).rglob("*.py")
            if reach.search(path.read_text())
        }
        # logging.py defines and configures the channel; api_keys.py owns
        # record_audit, which everything else imports.
        assert reaching == {"src/core/logging.py", "src/core/api_keys.py"}


class TestAuditFollowsTheCommit:
    """A record names a change the database kept, or it is not written (#100).

    Both functions used to emit as they flushed, before the caller chose
    between commit and rollback. A `rotate_key.py --dry-run` then left an
    "api key revoked" record for a key still live, and the real run left a
    second — two of those sit in the production journal, listed on #100.
    Revocation is a DELETE (#62), so this channel is the only account of
    which key died and when; a record of a change that was rolled back is a
    credential reported dead while it still authenticates.
    """

    async def test_a_mint_records_nothing_until_it_commits(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

        await mint(db_session, tenant.id, "pending", "production")
        assert _audit(caplog) == []

        await db_session.commit()
        assert [r.message for r in _audit(caplog)] == ["api key minted"]

    async def test_a_rolled_back_mint_records_nothing(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

        await mint(db_session, tenant.id, "rehearsal", "production")
        await db_session.rollback()

        assert _audit(caplog) == []

    async def test_a_revoke_records_nothing_until_it_commits(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        key, _ = await mint(db_session, tenant.id, "doomed", "production")
        await mint(db_session, tenant.id, "survivor", "production")
        await db_session.commit()
        caplog.clear()

        await revoke(db_session, tenant.id, key.id)
        assert _audit(caplog) == []

        await db_session.commit()
        assert [r.message for r in _audit(caplog)] == ["api key revoked"]

    async def test_a_rolled_back_revoke_records_nothing(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        key, _ = await mint(db_session, tenant.id, "spared", "production")
        await mint(db_session, tenant.id, "survivor", "production")
        await db_session.commit()
        caplog.clear()

        await revoke(db_session, tenant.id, key.id)
        await db_session.rollback()

        assert _audit(caplog) == []

    async def test_a_rotation_records_both_halves_in_order(self, db_session, tenant, caplog):
        """Mint first, then revoke — the order the transaction did them in,
        and the order an operator reads a rotation back in."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        old, _ = await mint(db_session, tenant.id, "old", "production")
        old_id = str(old.id)
        await db_session.commit()
        caplog.clear()

        await mint(db_session, tenant.id, "new", "production")
        await revoke(db_session, tenant.id, old_id)
        await db_session.commit()

        assert [(r.message, r.label) for r in _audit(caplog)] == [
            ("api key minted", "new"),
            ("api key revoked", "old"),
        ]

    async def test_a_rolled_back_rotation_records_nothing(self, db_session, tenant, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        old, _ = await mint(db_session, tenant.id, "old", "production")
        old_id = str(old.id)
        await db_session.commit()
        caplog.clear()

        await mint(db_session, tenant.id, "new", "production")
        await revoke(db_session, tenant.id, old_id)
        await db_session.rollback()

        assert _audit(caplog) == []

    async def test_a_commit_that_raises_records_nothing(self, db_session, tenant, caplog):
        """The case #100 named beside the dry run: a commit that fails after
        the mint flushed. The record must wait on the commit succeeding, not
        on the commit being attempted."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        await mint(db_session, tenant.id, "doomed by its neighbour", "production")
        db_session.add(
            ApiKey(
                tenant_id=tenant.id,
                label="breaks the commit",
                key_prefix="nk_xxxxx",
                key_hash=hash_key("unused"),
                environment="staging",  # outside the CheckConstraint
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

        assert _audit(caplog) == []

    async def test_a_record_does_not_outlive_its_transaction(self, db_session, tenant, caplog):
        """A record queued in a transaction that rolled back must not ride
        along into the next one and be emitted by *its* commit."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        tenant_id = str(tenant.id)
        await db_session.commit()

        await mint(db_session, tenant_id, "abandoned", "production")
        await db_session.rollback()
        await mint(db_session, tenant_id, "kept", "production")
        await db_session.commit()

        assert [r.label for r in _audit(caplog)] == ["kept"]

    async def test_a_record_does_not_outlive_a_closed_session(self, db_session, tenant, caplog):
        """Closing ends the transaction without a rollback call, and a closed
        AsyncSession can be used again — the queue must end with it."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        tenant_id = str(tenant.id)
        await db_session.commit()

        await mint(db_session, tenant_id, "abandoned", "production")
        await db_session.close()
        await mint(db_session, tenant_id, "kept", "production")
        await db_session.commit()

        assert [r.label for r in _audit(caplog)] == ["kept"]

    async def test_a_savepoint_rolled_back_later_keeps_the_records(
        self, db_session, tenant, caplog
    ):
        """Only the end of the whole transaction settles a record. A
        savepoint opened after the mint, and abandoned, leaves the mint
        standing — dropping its record there would be #67 again."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)

        await mint(db_session, tenant.id, "kept", "production")
        savepoint = await db_session.begin_nested()
        await savepoint.rollback()
        await db_session.commit()

        assert [r.label for r in _audit(caplog)] == ["kept"]

    async def test_refuses_to_mint_inside_a_savepoint(self, db_session, tenant, caplog):
        """A savepoint can roll back while its transaction commits, and the
        commit would then record a key that never existed. Refused rather
        than modelled: no caller needs one."""
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER_NAME)
        tenant_id = str(tenant.id)

        async with db_session.begin_nested():
            with pytest.raises(SavepointError):
                await mint(db_session, tenant_id, "nested", "production")

        assert await _count(db_session, tenant_id) == 0

    async def test_refuses_to_revoke_inside_a_savepoint(self, db_session, tenant):
        key, _ = await mint(db_session, tenant.id, "spared", "production")
        await mint(db_session, tenant.id, "survivor", "production")
        key_id = str(key.id)
        tenant_id = str(tenant.id)
        await db_session.commit()

        async with db_session.begin_nested():
            with pytest.raises(SavepointError):
                await revoke(db_session, tenant_id, key_id)

        assert await _count(db_session, tenant_id) == 2
