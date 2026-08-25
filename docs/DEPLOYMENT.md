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

# Install systemd units — production on :9000, dev endpoint on :9001
sudo cp deploy/notifier.service deploy/notifier-dev.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now notifier notifier-dev
```

## Production database opt-in

`deploy/notifier.service` carries `Environment=NOTIFIER_ALLOW_PROD_DB=1`. This
is what lets the live service open the production database past the guard in
`src/core/db_safety.py`. **Keep it in the unit.** Both `EnvironmentFile=`
paths on that unit — `/etc/notifier/.env` and the repo `.env` — are sourced by
humans and agents in ordinary shells; a flag placed in either would be
inherited by every one of them and would re-open the hole the guard closes
(issue #22).

## The dev endpoint (:9001)

`deploy/notifier-dev.service` serves `notifier_dev` on port 9001, enabled at
boot alongside the production unit. It exists because consumers need a base
URL that accepts a `development`-marked key: production refuses those at the
auth layer by design, and before #24 the only such endpoint was a foreground
`scripts/dev_server.sh` that stopped whenever its shell went away.

Three properties are load-bearing, each with a drift test in
`tests/deploy/test_dev_systemd_unit.py`:

- **No `NOTIFIER_ALLOW_PROD_DB`.** The production opt-in belongs to
  `notifier.service` alone. On this unit it would let the dev endpoint open
  the production database, undoing the whole point of a development key.
- **`ExecStart` is `scripts/dev_server.sh`, not a uvicorn line.** The script
  unsets the opt-in, swaps in `DEV_DATABASE_URL`, delegates the URL check to
  `src.core.db_safety`, and refuses an unmigrated database (#23). A second
  uvicorn spelling in the unit would be a second code path that can drift out
  from under all four.
- **`NOTIFIER_DEV_RELOAD=0`.** A wedged reloader keeps running after a syntax
  error on `main`, so `Restart=on-failure` never fires and the endpoint dies
  silently while systemd reports it active.

`StartLimitBurst=5` bounds the restart loop: an unreachable or unmigrated
`notifier_dev` makes the script exit non-zero on purpose, and without the
bound that is a 5-second retry in the journal forever.

To run a branch by hand, stop the unit first — it holds the port:

```bash
sudo systemctl stop notifier-dev
./scripts/dev_server.sh          # foreground, --reload on
sudo systemctl start notifier-dev
```

## Routine ops

```bash
# Restart after code merge — both units run the same working tree
sudo systemctl restart notifier notifier-dev

# Apply pending migrations then restart. alembic/env.py reads DATABASE_URL
# directly and is deliberately exempt from the db_safety guard — production is
# the correct target here. The dev database needs the same migration, or
# notifier-dev refuses to start (#23).
. scripts/load_env.sh
uv run alembic upgrade head
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
sudo systemctl restart notifier notifier-dev

# Logs
sudo journalctl -u notifier -f
sudo journalctl -u notifier-dev -f
```

## Future: split VM

Once the v0 API has held still for a few weeks, provision a separate exe.dev VM and pg_dump → restore the `notifier` database there. Update watcher's `WATCHER_NOTIFIER_BASE_URL` — and `WATCHER_DEV_NOTIFIER_BASE_URL`, which points at :9001 — to the new host. Decommission the local notifier service on watcher's VM.

Note the VM is currently named `watcher`, so the exe.dev proxy serves these as `https://watcher.exe.xyz:9000/` and `https://watcher.exe.xyz:9001/`. Co-located consumers should use `http://localhost:<port>` and skip the proxy entirely.

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
