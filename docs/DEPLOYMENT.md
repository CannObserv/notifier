# Deployment

Single-VM setup; co-located with `watcher` for the v0 phase.

## First-time setup

```bash
# Install Python 3.12+ and uv (already present on the shared VM)
# Create the production env file
sudo mkdir -p /etc/notifier
sudo tee /etc/notifier/.env > /dev/null <<'EOF'
DATABASE_URL=postgresql+asyncpg://notifier:notifier@localhost:5432/notifier
NOTIFIER_SECRET_KEY=<paste Fernet key here>
EOF
sudo chmod 640 /etc/notifier/.env

# Provision Postgres
sudo -u postgres psql -c "CREATE USER notifier WITH PASSWORD 'notifier';"
sudo -u postgres psql -c "CREATE DATABASE notifier OWNER notifier;"
sudo -u postgres psql -c "CREATE DATABASE notifier_test OWNER notifier;"
sudo -u postgres psql -c "CREATE DATABASE notifier_dev OWNER notifier;"

# Install dependencies + apply migrations
cd /home/exedev/notifier
uv sync
. scripts/load_env.sh
uv run alembic upgrade head
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head   # dev DB, if configured

# Install systemd unit
sudo cp deploy/notifier.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now notifier
```

## Production database opt-in

`deploy/notifier.service` carries `Environment=NOTIFIER_ALLOW_PROD_DB=1`. This
is what lets the live service open the production database past the guard in
`src/core/db_safety.py`. **Keep it in the unit.** Both `EnvironmentFile=`
paths on that unit — `/etc/notifier/.env` and the repo `.env` — are sourced by
humans and agents in ordinary shells; a flag placed in either would be
inherited by every one of them and would re-open the hole the guard closes
(issue #22).

## Routine ops

```bash
# Restart after code merge
sudo systemctl restart notifier

# Apply pending migrations then restart. alembic/env.py reads DATABASE_URL
# directly and is deliberately exempt from the db_safety guard — production is
# the correct target here.
. scripts/load_env.sh
uv run alembic upgrade head && sudo systemctl restart notifier

# Logs
sudo journalctl -u notifier -f
```

## Future: split VM

Once the v0 API has held still for a few weeks, provision a separate exe.dev VM and pg_dump → restore the `notifier` database there. Update watcher's `NOTIFY_BASE_URL` to point at the new host. Decommission the local notifier service on watcher's VM.

## SocratiCode indexing (agent tooling)

Cross-project semantic search and context-artifact retrieval rely on two files:

- **`.socraticodecontextartifacts.json`** — committed catalog of non-code knowledge to index alongside source (DB schema migrations, deployment doc, ops runbook, systemd unit). Edit when adding new authoritative reference material.
- **`.claude/settings.local.json`** — gitignored, **per-VM**. Provides `SOCRATICODE_LINKED_PROJECTS` so the MCP server can search sibling projects (e.g. `watcher`).

On a fresh VM, create `.claude/settings.local.json` with absolute paths to any sibling repos you want linked:

```json
{
  "env": {
    "SOCRATICODE_LINKED_PROJECTS": "/home/exedev/watcher"
  }
}
```

Reload the VS Code window after creating or editing this file — the MCP server reads its env at session start, not on file change. Verify with a cross-project search; results should be tagged `[notifier]` or `[watcher]`.
