"""One-off helper to create a tenant + API key.

Usage:
    export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
    uv run python scripts/seed_tenant.py <tenant_name> <key_label>

Prints ``tenant_id`` and the raw API key. **The raw key is shown ONCE** — store
it in the consumer's secrets immediately. Only the SHA-256 hash is persisted.
"""

import asyncio
import hashlib
import secrets
import sys

from src.core.database import get_session_factory
from src.core.models import ApiKey, Tenant


async def main(tenant_name: str, key_label: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        tenant = Tenant(name=tenant_name)
        session.add(tenant)
        await session.flush()
        raw = "nk_" + secrets.token_urlsafe(32)
        session.add(
            ApiKey(
                tenant_id=tenant.id,
                label=key_label,
                key_prefix=raw[:8],
                key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )
        await session.commit()
        print(f"tenant_id={tenant.id}")
        print(f"raw_key={raw}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: seed_tenant.py <tenant_name> <key_label>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
