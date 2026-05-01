# Common Commands

## Setup

```bash
# Install dependencies (creates .venv automatically)
uv sync
```

## Environment

Two env files, loaded in order:

```bash
# Production secrets (DATABASE_URL, NOTIFIER_SECRET_KEY) — persistent, survives repo resets
/etc/notifier/.env

# Dev/agent secrets (GH_TOKEN, TEST_DATABASE_URL) — repo root, git-ignored
.env

# Load both for shell commands
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
```

The systemd service loads both automatically (see `deploy/notifier.service`).

## Service Management

The notifier service runs via systemd. **Always use systemctl** — never start uvicorn manually on port 9000.

```bash
# Restart after code changes (migrations are NOT auto-run)
sudo systemctl restart notifier

# Check status
sudo systemctl status notifier

# Follow logs
sudo journalctl -u notifier -f

# Reload systemd after editing deploy/notifier.service
sudo systemctl daemon-reload && sudo systemctl restart notifier
```

## Development

```bash
# Dev server — use port 9001 so the systemd service stays up
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 9001 --reload
```

## Migrations

```bash
uv run alembic upgrade head                              # apply all migrations
uv run alembic revision --autogenerate -m "description"  # generate new migration
uv run alembic downgrade -1                              # roll back one
```

## Testing

```bash
uv run pytest                          # default: -m 'not integration'
uv run pytest -m integration           # integration tests (require live DB)
uv run pytest --no-cov                 # skip coverage
uv run ruff check .                    # lint
```

## Generating a Fernet key

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## SDK regeneration

```bash
# Regenerate the Python SDK from notifier's OpenAPI schema
clients/python/scripts/regen.sh

# Verify SDK is not stale (mirrors CI)
git diff --exit-code clients/python/src/notifier_client/generated/
```

## SDK integration tests

Gated on `TEST_DATABASE_URL`. The fixture creates the schema in that DB,
spawns a uvicorn on an ephemeral port wired to it, seeds a tenant, and drops
the schema on teardown. Every subprocess receives `DATABASE_URL=$TEST_DATABASE_URL`,
so production cannot be polluted.

```bash
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
cd clients/python && uv run pytest -m integration
```

Skips with a message if `TEST_DATABASE_URL` is unset.

## Generating a tenant + API key (until admin UI exists)

For v0, tenants and API keys are seeded via SQL or a one-off Python script. Example:

```bash
uv run python -c "
import asyncio, hashlib, secrets
from src.core.database import get_session_factory
from src.core.models import ApiKey, Tenant

async def main():
    factory = get_session_factory()
    async with factory() as s:
        t = Tenant(name='watcher')
        s.add(t)
        await s.flush()
        raw = 'nk_' + secrets.token_urlsafe(32)
        s.add(ApiKey(
            tenant_id=t.id, label='watcher-prod',
            key_prefix=raw[:8],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        ))
        await s.commit()
        print(f'tenant_id={t.id}\nraw_key={raw}')

asyncio.run(main())
"
```
