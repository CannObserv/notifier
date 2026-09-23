"""Copy channels between tenants without the Apprise URL ever leaving the database.

Onboarding a consumer onto the cohort's existing Slack and Mailgun
destinations meant reading the Apprise URL from somewhere and pasting it into
``POST /channels``. That is the one onboarding step that puts a live
credential in an operator's clipboard or an agent's transcript. The API only
returns a masked URL, so no API path avoids it.

It does not have to happen. Every channel is encrypted under one server key
(``src/core/crypto.py``), and a Fernet token carries no associated data, so
nothing binds a ciphertext to the tenant that owns it. The stored token is
copied **verbatim**. It is never decrypted here, so this module cannot leak
what it never holds.

Tenancy is the reason this is a script path and never an API one. A tenant
reaching into another tenant's channels is exactly what the auth layer
forbids. An operator granting one tenant a copy of another's destination is
configuration, so it lives beside ``seed_tenant.py`` and ``delete_tenant.py``.

**A copy is a grant.** The target tenant can then deliver to that Slack
workspace or those mail recipients, which is why every copy is recorded on
the credential audit channel. The records name both ends and never the URL.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api_keys import TenantNotFoundError, ulid_str
from src.core.logging import get_audit_logger
from src.core.models import Channel, Tenant

audit = get_audit_logger()


class ChannelNotFoundError(LookupError):
    """Raised when a source channel does not exist."""


class SameTenantError(ValueError):
    """Raised when a channel would be copied into the tenant that owns it."""


class ChannelNameTakenError(ValueError):
    """Raised when the target already has, or the run repeats, a channel name.

    The schema does not make names unique. Without this refusal a re-run
    would quietly give the target a second copy of every channel.
    """


@dataclass(frozen=True, slots=True)
class ChannelCopy:
    """One copy made (or rehearsed): both ends, and never the URL."""

    source_channel_id: str
    source_tenant_id: str
    channel_id: str
    tenant_id: str
    name: str
    channel_hint: str | None


async def copy_channels(
    session: AsyncSession,
    to_tenant_id: str,
    copies: list[tuple[str, str]],
    *,
    dry_run: bool = True,
) -> list[ChannelCopy]:
    """Copy each ``(source_channel_id, new_name)`` into *to_tenant_id*.

    All or nothing: every refusal fires before the first row is added, and
    under ``dry_run`` too. A rehearsal that passes where the real run would
    fail certifies the wrong thing.

    ``dry_run`` is the default and rolls back, emitting nothing. This matches
    :func:`~src.core.tenants.delete_tenant`, so a caller that forgets the flag
    writes nothing. On a real run the commit comes first and the records
    after it. A record of a grant that then failed to commit would report
    access that nobody has.
    """
    to_tenant_id = ulid_str(to_tenant_id)
    try:
        if await session.get(Tenant, to_tenant_id) is None:
            raise TenantNotFoundError(f"no tenant with id {to_tenant_id}")

        existing = set(
            (
                await session.execute(select(Channel.name).where(Channel.tenant_id == to_tenant_id))
            ).scalars()
        )
        planned: list[tuple[Channel, str]] = []
        for source_id, new_name in copies:
            source = await session.get(Channel, ulid_str(source_id))
            if source is None:
                raise ChannelNotFoundError(f"no channel with id {source_id}")
            if ulid_str(source.tenant_id) == to_tenant_id:
                raise SameTenantError(
                    f"channel {source_id} already belongs to tenant {to_tenant_id}"
                )
            if new_name in existing:
                raise ChannelNameTakenError(
                    f"tenant {to_tenant_id} already has a channel named {new_name!r}"
                )
            existing.add(new_name)
            planned.append((source, new_name))

        made: list[ChannelCopy] = []
        for source, new_name in planned:
            copy = Channel(
                tenant_id=to_tenant_id,
                name=new_name,
                apprise_url_encrypted=source.apprise_url_encrypted,
                channel_hint=source.channel_hint,
            )
            session.add(copy)
            await session.flush()
            made.append(
                ChannelCopy(
                    source_channel_id=ulid_str(source.id),
                    source_tenant_id=ulid_str(source.tenant_id),
                    channel_id=ulid_str(copy.id),
                    tenant_id=to_tenant_id,
                    name=new_name,
                    channel_hint=source.channel_hint,
                )
            )
    except Exception:
        await session.rollback()
        raise

    if dry_run:
        await session.rollback()
        return made

    await session.commit()
    for copy in made:
        audit.info(
            "channel copied",
            extra={
                "source_tenant_id": copy.source_tenant_id,
                "source_channel_id": copy.source_channel_id,
                "tenant_id": copy.tenant_id,
                "channel_id": copy.channel_id,
                "channel_name": copy.name,
                "channel_hint": copy.channel_hint,
            },
        )
    return made
