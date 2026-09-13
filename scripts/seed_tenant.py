"""One-off helper to create a tenant + API key.

Creates a **new** tenant, always. To attach a key to a tenant that already
exists, to revoke one, or to rotate — use ``scripts/rotate_key.py``. That
split is deliberate: a script named ``seed_tenant`` that sometimes deletes
credentials is the wrong thing to find during an incident (#62).

Usage (dev database — served by notifier-dev.service on :9001):
    . scripts/load_env.sh
    DATABASE_URL="$DEV_DATABASE_URL" \
        uv run python scripts/seed_tenant.py <name> <label> [environment]

Usage (production — deliberate, opt-in):
    . scripts/load_env.sh
    NOTIFIER_ALLOW_PROD_DB=1 \
        uv run python scripts/seed_tenant.py <name> <label> [environment]

This script opens a connection through ``src.core.database``, so the guard in
``src/core/db_safety.py`` applies: seeding production requires the explicit
opt-in above. Pass it on the command line for the single invocation — never
add it to an env file.

``environment`` is ``production`` (default) or ``development``. A production
deployment refuses development keys at the auth layer, so a key minted for a
consumer's test suite cannot reach production notifier even if it leaks into
the wrong config (issue #22, finding 3).

Prints ``tenant_id`` and the raw API key. **The raw key is shown ONCE** — store
it in the consumer's secrets immediately. Only the SHA-256 hash is persisted.

The argv shape here is load-bearing beyond an operator's hands:
``clients/python/tests/conftest.py`` shells this script positionally and parses
its stdout. Adding a flag is fine; moving or renaming the two positional
arguments, or the ``key=value`` output lines, breaks that fixture.
"""

import asyncio
import sys

from src.core.api_keys import ENVIRONMENTS, mint
from src.core.database import get_session_factory
from src.core.models import Tenant


async def main(tenant_name: str, key_label: str, environment: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        tenant = Tenant(name=tenant_name)
        session.add(tenant)
        await session.flush()
        _key, raw = await mint(session, tenant.id, key_label, environment)
        await session.commit()
        print(f"tenant_id={tenant.id}")
        print(f"raw_key={raw}")
        print(f"environment={environment}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(
            "usage: seed_tenant.py <tenant_name> <key_label> [production|development]",
            file=sys.stderr,
        )
        sys.exit(2)
    env = sys.argv[3] if len(sys.argv) == 4 else "production"
    if env not in ENVIRONMENTS:
        print(f"environment must be production or development, got {env!r}", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2], env))
