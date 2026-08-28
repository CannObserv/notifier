# Deployment

Own VM since #43: `notifier.exe.xyz` (exe.dev, `pdx`) runs this service and its
PostgreSQL 16 cluster and nothing else. Consumers reach it over the
`cannobserv.org.github` tailnet — see
[reference/tailscale.md](reference/tailscale.md).

## First-time setup

```bash
# The exeuntu image already ships Python 3.12, uv, git — and, as of 2026-08,
# Tailscale itself (inactive). Join the tailnet first: both units bind this
# host's tailnet address and will not start without one.
sudo install -m 600 /dev/null /run/ts.key
sudo tee /run/ts.key >/dev/null <<< 'tskey-auth-...'   # pre-approved + tag:notifier + NOT ephemeral
sudo systemctl enable --now tailscaled
sudo tailscale up --auth-key=file:/run/ts.key --hostname=notifier
sudo shred -u /run/ts.key
tailscale ip -4

sudo apt-get install -y postgresql-16 postgresql-client-16

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

# Point the dev endpoint at the dev database. This MUST exist before
# notifier-dev is enabled below: the unit runs scripts/dev_server.sh, which
# refuses to start without DEV_DATABASE_URL, and five such refusals trip
# StartLimitBurst and leave the unit failed until `systemctl reset-failed`.
# The repo .env is git-ignored; DEV_DATABASE_URL never belongs in
# /etc/notifier/.env, which is the production file.
cd /home/exedev/notifier
grep -q '^DEV_DATABASE_URL=' .env 2>/dev/null || \
  echo 'DEV_DATABASE_URL=postgresql+asyncpg://notifier:notifier@localhost:5432/notifier_dev' >> .env

# Install dependencies + apply migrations — both databases, since an
# unmigrated notifier_dev also refuses to start (#23)
uv sync
. scripts/load_env.sh
uv run alembic upgrade head
DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head

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

`StartLimitBurst=5` at `RestartSec=15` bounds the restart loop: an
unreachable, unconfigured, or unmigrated `notifier_dev` makes the script exit
non-zero on purpose, and without the bound that is a retry in the journal
forever. 75 seconds of retries is long enough to ride out a slow Postgres at
boot — `After=` orders startup but does not wait for the cluster to accept
connections — and short enough that a real misconfiguration gives up somewhere
a human will see it. A unit that trips the limit stays failed:

```bash
sudo systemctl reset-failed notifier-dev && sudo systemctl start notifier-dev
```

The unit also writes `/run/notifier/build-id-dev`, its own file rather than
the production unit's `build-id`, so `:9001/health` names the commit it is
serving without the two units racing to write one path.

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

## Health checks

**On this VM, `curl http://127.0.0.1:9000/health` fails — so does
`http://notifier:9000`.** The units bind the tailnet address alone, and
Ubuntu's `/etc/hosts` maps the hostname `notifier` to `127.0.1.1`, so the short
name resolves locally instead of through MagicDNS:

```bash
curl "http://$(tailscale ip -4):9000/health"     # this VM
curl http://notifier:9000/health                 # any other tailnet node
```

`https://notifier.exe.xyz:9000/` reaches the exe.dev login gate and stops
there: nothing listens on the interface the proxy forwards to. Deliberate.

## The VM split (#43, done)

Notifier ran co-located on the `watcher` VM through v0, reached at
`http://localhost:9000`. #43 moved it here and replaced that hop with the
tailnet. The migration record — including the `pg_dump`/restore, the Fernet-key
verification gate, and the rollback path — is in that issue.

## SocratiCode indexing (agent tooling)

Cross-project semantic search and context-artifact retrieval rely on two files:

- **`.socraticodecontextartifacts.json`** — committed catalog of non-code knowledge to index alongside source (DB schema migrations, deployment doc, ops runbook, systemd unit). Edit when adding new authoritative reference material.
- **`.claude/settings.local.json`** — gitignored, **per-VM**. Provides `SOCRATICODE_LINKED_PROJECTS` so the MCP server can search sibling projects.

**Since #43 there are no sibling repos on this host** — it runs notifier alone,
so there is nothing local to link. The setting stays documented because the
sibling checkouts live on the `watcher` VM, and an agent working there against
this repo would still want it:

```json
{
  "env": {
    "SOCRATICODE_LINKED_PROJECTS": "/home/exedev/watcher"
  }
}
```

Reload the VS Code window after creating or editing this file — the MCP server reads its env at session start, not on file change. Verify with a cross-project search; results should be tagged `[notifier]` or `[watcher]`.
