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

# Dev/agent secrets (GH_TOKEN, TEST_DATABASE_URL, DEV_DATABASE_URL) — repo root, git-ignored
.env

# Load both for shell commands. Source them; do not word-split through xargs,
# which corrupts values containing spaces or quotes.
. scripts/load_env.sh
```

The systemd service loads both automatically (see `deploy/notifier.service`).

**Loading these leaves `DATABASE_URL` pointing at production.** That is the
intended target for `alembic upgrade head` — on this single-VM setup `main`
*is* the deployed code — and wrong for everything else:

| Want | Use | Database |
|---|---|---|
| Dev endpoint (:9001) | `sudo systemctl restart notifier-dev` | `notifier_dev` |
| Dev server by hand | `./scripts/dev_server.sh` | `notifier_dev` |
| Tests | `uv run pytest` | `notifier_test` (pinned by `tests/conftest.py`) |
| Migrations | `uv run alembic upgrade head` | production, deliberately |

`src/core/db_safety.py` refuses any database whose name does not end in
`_test` or `_dev`. The opt-in `NOTIFIER_ALLOW_PROD_DB=1` lives in
`deploy/notifier.service` and must never be added to an env file — every
process that sources the file would inherit it.

## Service Management

The notifier service runs via systemd. **Always use systemctl** — never start uvicorn manually on port 9000.

```bash
# Restart after code changes (migrations are NOT auto-run)
sudo systemctl restart notifier

# Check status
sudo systemctl status notifier

# Follow logs
sudo journalctl -u notifier -f

# Reload systemd after editing either unit in deploy/
sudo systemctl daemon-reload && sudo systemctl restart notifier notifier-dev
```

The dev endpoint on 9001 is a second unit, `notifier-dev.service`, serving
`notifier_dev`. It is the base URL consumers point their non-production
processes at (#24) — 9000 refuses `development`-marked keys.

```bash
sudo systemctl restart notifier-dev
sudo systemctl status notifier-dev
sudo journalctl -u notifier-dev -f
curl http://127.0.0.1:9001/health
```

It launches `scripts/dev_server.sh`, so it inherits every guard that script
carries: the production opt-in is unset, `DATABASE_URL` comes from
`DEV_DATABASE_URL`, the URL check is `src.core.db_safety`, and an unmigrated
dev database refuses to start rather than 500 on every request (#23). If the
unit will not come up, that last one is the usual reason — the journal names
it:

```bash
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
```

## Development

```bash
# Dev server by hand — same script the notifier-dev unit runs, with --reload
# on. The unit holds port 9001, so stop it first and hand it back after.
# Never hand-run uvicorn; see issue #22.
sudo systemctl stop notifier-dev
./scripts/dev_server.sh
sudo systemctl start notifier-dev
```

First-time setup of the dev database:

```bash
sudo -u postgres psql -c "CREATE DATABASE notifier_dev OWNER notifier;"
echo 'DEV_DATABASE_URL=postgresql+asyncpg://notifier:PASSWORD@localhost:5432/notifier_dev' >> .env
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
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
uv run ruff format .                   # format
uv run ruff format --check .           # format gate (as run by CI's lint job)
```

## Lint & format gates

`ruff check` and `ruff format --check` run as separate steps in CI's `lint`
job and are wired into pre-commit, so a plain `git commit` enforces them
locally too:

```bash
uv run pre-commit install              # one-time, per clone
uv run pre-commit run --all-files      # run both gates over the whole repo
git commit --no-verify                 # escape hatch — gates still fail at ship time
```

The hooks shell out to `uv run ruff`, so they use the exact ruff pinned in
`uv.lock` — the same binary CI installs with `uv sync --locked`. No version
skew. Note the hooks stop there: **pre-commit runs no tests**, so only CI
says whether the suite passes.


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
. scripts/load_env.sh
cd clients/python && uv run pytest -m integration
```

Skips with a message if `TEST_DATABASE_URL` is unset.

## Generating a tenant + API key (until admin UI exists)

Use `scripts/seed_tenant.py`. The third argument marks which deployment the
key is for — `production` (default) or `development`. **A production
deployment refuses `development` keys at the auth layer** (403), which is the
layer that catches a consumer's test suite calling production over HTTP; no
database guard can see that vector (issue #22, finding 3).

```bash
. scripts/load_env.sh

# Dev tenant, on the dev database (served by notifier-dev.service on :9001)
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/seed_tenant.py acme acme-dev development

# Production tenant — deliberate, opt-in, on the command line only
NOTIFIER_ALLOW_PROD_DB=1 \
  uv run python scripts/seed_tenant.py acme acme-prod production
```

Prints `tenant_id`, `raw_key`, and `environment`. **The raw key is shown
once** — only its SHA-256 hash is stored.

This VM already has a `dev` tenant with a `development` key in `notifier_dev`;
the key is in the repo `.env` as `DEV_TENANT_API_KEY`. It also has a `watcher`
tenant there, minted for watcher's non-production processes (watcher#278 step
2); that key lives in watcher's own `.env` as `WATCHER_DEV_NOTIFIER_API_KEY`,
not in this repo.

**Hand a consumer both halves, never just the key:** base URL
`http://localhost:9001` for anything co-located on this VM, and a key minted
`development`. The pair only works together — a development key against
`http://localhost:9000` is rejected, which is the point.

### Seeding the dev tenant's sink channels

A dev tenant with a key and no channels can authenticate but cannot dispatch
(#26). `scripts/seed_dev_channels.py` gives one two sinks, neither of which
reaches a real recipient:

```bash
. scripts/load_env.sh
DATABASE_URL="$DEV_DATABASE_URL" \
  uv run python scripts/seed_dev_channels.py watcher
```

| Channel | Apprise URL | Outcome | Why |
|---|---|---|---|
| `dev-sink` | `syslog://local7` | succeeds | Lands in this VM's journal — `sudo journalctl -t Notifier` shows the rendered payload, so a consumer can read back what it sent |
| `dev-sink-failing` | `json://127.0.0.1:1/sink` | fails | Port 1 is privileged and unroutable, so the refusal is structural. Lets a consumer exercise error handling without waiting for a real outage |

Safe to re-run; existing channels are left alone. It refuses any database whose
name does not end in `_dev` — **including with `NOTIFIER_ALLOW_PROD_DB=1` set**,
which is deliberate: seeding fixture rows is never a production operation, and
fixture channels in the production tenant is the shape of the incident behind
watcher#278.

### Dev channels are sink channels by construction

`notifier_dev` is a separate database from `notifier`, so the production Slack
and Mailgun channel rows do not exist in it. A dev dispatch has nothing real
to reach unless someone deliberately seeds a live Apprise URL into the dev
database. Do not "helpfully" copy production channels across — that recreates
the exact failure watcher#278 documents, where ~1289 fixture notifications
were delivered to real recipients.
