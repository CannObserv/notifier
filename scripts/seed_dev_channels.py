"""Seed the dev tenant's sink channels.

The dev tenant shipped with a working API key and nothing to dispatch to, so
watcher could authenticate and construct a client but never exercise the
notification path end to end (#26; the ask in CannObserv/watcher#278 step 2).

Two sinks, because "can dispatch" is two questions:

* ``dev-sink`` — ``syslog://``. Apprise reports success, and the payload lands
  in this VM's journal, so a consumer debugging a fan-out can read what it
  sent (``journalctl -t Notifier``). Reaches no subscriber.
* ``dev-sink-failing`` — a port nothing binds. Deterministic failure, so a
  consumer can exercise its error handling without waiting for a real
  outage.

Usage:
    . scripts/load_env.sh
    DATABASE_URL="$DEV_DATABASE_URL" \
        uv run python scripts/seed_dev_channels.py <tenant_name>

Safe to re-run: existing channels are left alone and only new ones are
created.
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.crypto import encrypt_apprise_url
from src.core.database import get_session_factory
from src.core.models import Channel, Tenant

#: Suffix a database must carry to be seeded with fixture rows.
DEV_SUFFIX = "_dev"


class WrongDatabaseError(RuntimeError):
    """Raised when the target database is not a dev database."""


@dataclass(frozen=True, slots=True)
class SinkSpec:
    """A channel this script guarantees exists on the dev tenant."""

    name: str
    apprise_url: str
    channel_hint: str
    expected_outcome: str  # "succeeds" | "fails"


DEV_SINKS: tuple[SinkSpec, ...] = (
    SinkSpec(
        name="dev-sink",
        apprise_url="syslog://local7",
        channel_hint="syslog",
        expected_outcome="succeeds",
    ),
    SinkSpec(
        # Port 1 is privileged and unroutable, so the refusal is structural
        # rather than depending on nothing happening to bind a high port.
        name="dev-sink-failing",
        apprise_url="json://127.0.0.1:1/sink",
        channel_hint="sink",
        expected_outcome="fails",
    ),
)


def assert_dev_database(url: str) -> None:
    """Refuse any database that is not the dev database.

    Deliberately stricter than :mod:`src.core.db_safety`, which admits ``_test``
    as well and honours ``NOTIFIER_ALLOW_PROD_DB`` for deliberate production
    work. Seeding fixture rows is never deliberate production work, so this has
    no escape hatch — the failure mode it guards against is fixture channels
    appearing in the production tenant, which is the shape of the incident
    that started all of this (watcher#278).
    """
    name = urlsplit(url).path.lstrip("/")
    if not name.endswith(DEV_SUFFIX):
        raise WrongDatabaseError(
            f"Refusing to seed dev channels into {name!r}: expected a database "
            f"name ending in {DEV_SUFFIX}. Point DATABASE_URL at DEV_DATABASE_URL."
        )


async def seed(session: AsyncSession, tenant_id: str) -> list[Channel]:
    """Create any missing sink channels for *tenant_id*; return the new ones."""
    existing = set(
        (
            await session.execute(select(Channel.name).where(Channel.tenant_id == tenant_id))
        ).scalars()
    )
    created: list[Channel] = []
    for spec in DEV_SINKS:
        if spec.name in existing:
            continue
        channel = Channel(
            tenant_id=tenant_id,
            name=spec.name,
            apprise_url_encrypted=encrypt_apprise_url(spec.apprise_url),
            channel_hint=spec.channel_hint,
        )
        session.add(channel)
        created.append(channel)
    await session.flush()
    return created


async def main(tenant_name: str) -> int:
    assert_dev_database(os.environ.get("DATABASE_URL", ""))
    factory = get_session_factory()
    async with factory() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.name == tenant_name))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"no tenant named {tenant_name!r} in this database", file=sys.stderr)
            return 1
        created = await seed(session, tenant.id)
        await session.commit()
        for channel in created:
            print(f"created {channel.name} id={channel.id}")
        if not created:
            print("all sink channels already present")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: seed_dev_channels.py <tenant_name>", file=sys.stderr)
        sys.exit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
