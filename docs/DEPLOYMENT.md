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

# Install systemd units — production on :9000, dev endpoint on :9001, plus
# the two dead-man's-timer sweeps (#56). The sweep *timers* are enabled; their
# .service units are started by the timers and must not be enabled themselves.
sudo cp deploy/notifier.service deploy/notifier-dev.service \
        deploy/notifier-sweep.service deploy/notifier-sweep.timer \
        deploy/notifier-sweep-dev.service deploy/notifier-sweep-dev.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now notifier notifier-dev
sudo systemctl enable --now notifier-sweep.timer notifier-sweep-dev.timer

# Memory reservation for the production units (#74). This host is 3.8 GiB with
# no swap and shares a kernel with agent sessions; see the section below.
sudo cp deploy/99-notifier-memory.conf /etc/sysctl.d/
sudo cp deploy/earlyoom.default /etc/default/earlyoom
sudo sysctl -p /etc/sysctl.d/99-notifier-memory.conf
sudo apt-get install -y earlyoom
sudo systemctl enable --now earlyoom
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

## Environment variables

The per-variable reference. The two-file model, and the trap that
`. scripts/load_env.sh` leaves `DATABASE_URL` pointing at **production**, are
in the policy file instead — nearly every task needs those two facts and almost
none needs this list.

Currently defined:
- `DATABASE_URL` — PostgreSQL connection string (in `/etc/notifier/.env`)
- `GH_TOKEN` — GitHub personal access token (in `.env`)
- `TEST_DATABASE_URL` — PostgreSQL connection string for the test database `notifier_test` (in `.env`); `tests/conftest.py` pins `DATABASE_URL` to it for the whole session
- `DEV_DATABASE_URL` — PostgreSQL connection string for the dev database `notifier_dev` (in `.env`); `scripts/dev_server.sh` requires it, so `notifier-dev.service` does too
- `NOTIFIER_DEV_RELOAD` — `0` disables uvicorn's reloader in `scripts/dev_server.sh`; set in `deploy/notifier-dev.service` only, defaults to on for a hand-run server
- `DEV_TENANT_API_KEY` — API key for the `dev` tenant in `notifier_dev` (in `.env`); marked `development`, so production refuses it
- `NOTIFIER_ALLOW_PROD_DB` — the production opt-in, and the one variable that must never reach an env file. Rule and reasoning: [Production database opt-in](#production-database-opt-in) above
- `BUILD_ID` — (optional) git SHA reported by `/health`; blank or unset both fall back to `"dev"`. Each systemd unit stamps its own file (`/run/notifier/build-id`, `/run/notifier/build-id-dev`) from `git rev-parse` at start
- `NOTIFIER_APP_URL` — (optional) branding URL embedded in delivered notifications. Unset means **no link**, which is the default: six Apprise plugins render it as a clickable link, and Apprise's own fallback is the Apprise GitHub repo. Set it only to an address that actually resolves. **Read once at import**, so a change needs a service restart before it takes effect
- `NOTIFIER_SECRET_KEY` — Fernet key for encrypting Apprise URLs at rest (in `/etc/notifier/.env`); `scripts/dev_server.sh` refuses to start without it, because a server that lacks it still answers `/ready` and fails only at the first dispatch; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `NOTIFIER_SWEEP_DEV` — `1` tells `scripts/sweep.sh` to load the env files itself and swap `DATABASE_URL` for `DEV_DATABASE_URL`, the same swap `dev_server.sh` performs. Set in `deploy/notifier-sweep-dev.service` only; the production sweep leaves it unset and takes `DATABASE_URL` from its own `EnvironmentFile`
- `NOTIFIER_BIND_HOST` — **tests and diagnosis only.** Overrides the tailnet
  probe in `scripts/tailnet_bind.sh` with a literal bind address. Never put it
  in an env file or a unit, for the same reason as `NOTIFIER_ALLOW_PROD_DB`: it
  would move the bind off the tailnet silently while every health check stayed
  green. CI sets it because CI has no tailnet;
  `tests/deploy/test_systemd_unit.py` asserts neither unit nor either env file
  carries it
- `NOTIFIER_TAILNET_WAIT_SECONDS` — how long `scripts/tailnet_bind.sh` waits for
  tailscaled to assign an address before failing the start (default 60). The
  unit's `StartLimit*` bound is sized around it

Reserved, not set:
- `PROCRASTINATE_DATABASE_URL` — libpq-style DSN for the future async dispatch worker. Set nowhere, read by nothing; procrastinate is uninstalled (#29). **Not covered by the `db_safety` guard** — it crosses no chokepoint, so route it through `assert_safe_database_url` when the worker lands.

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

# The sweeps are timers, not services — `systemctl status notifier-sweep`
# shows the last one-shot pass, which is normally `inactive (dead)`. What
# matters is that the timer is still scheduled.
systemctl list-timers 'notifier-sweep*'
sudo journalctl -u notifier-sweep -f
```

Restarting `notifier notifier-dev` picks up merged code for the API. The sweep
units read the same working tree at each firing, so they need no restart —
but `systemctl daemon-reload` is still required after editing anything in
`deploy/`.

### Worktrees here must not share this checkout's `.venv`

`.skills/worktree_venv` is committed holding `none`, which stops
`worktree-create.sh` symlinking this checkout's `.venv` into a new worktree.
Provision the worktree's own with `uv sync` — sub-second against a warm cache.

The reason is the line directly above: the sweep units read *this* working
tree, and `scripts/sweep.sh` reaches uvicorn's environment through `uv run`.
`notifier-sweep.timer` fires **every 60 seconds**, so a shared `.venv` hands a
worktree's test run an environment the live service is concurrently
reinstalling into. Two symptoms, neither of which looks like its cause:
`uv run` restamps `importlib.metadata.version(...)` to *main's* version
mid-run, and an `ExecStartPre=uv sync` prunes dependency groups it was not
asked for — turning modules that `pytest.importorskip` at import time into
**skips that still report green**.

It is committed rather than left untracked because the cost is asymmetric. On
a clone with no sweep timer — a laptop, CI — `none` costs one `uv sync` per
worktree. On this VM rebuilt or re-cloned without it, the protection is
silently absent and the failure reports success. The `using-git-worktrees`
skill frames this as a property of one machine rather than of the repo, which
is true; committing it trades a trivial cost on clones that do not need it for
a silent one on the clone that does.

## Health checks

**On this VM, `curl http://127.0.0.1:9000/health` fails — so does
`http://notifier:9000`.** The units bind the tailnet address alone, and
Ubuntu's `/etc/hosts` maps the hostname `notifier` to `127.0.1.1`, so the short
name resolves locally instead of through MagicDNS:

```bash
curl "http://$(tailscale ip -4):9000/health"     # this VM
curl http://notifier:9000/health                 # any other tailnet node
```

Both ports answer, and the payload says which one you reached:

```json
{"status": "ok", "build": "4d949e8", "database": "notifier",     "environment": "production"}
{"status": "ok", "build": "4d949e8", "database": "notifier_dev", "environment": "development"}
```

**`build` is the same on both and always will be** — the two units serve one
working tree, so a matching SHA confirms nothing about which port answered
(#58). Read `environment`. `/health` reports it from the configured URL;
`/ready` reports the database actually connected, via `current_database()`, so
`/health` and `/ready` disagreeing means the running engine and `DATABASE_URL`
have diverged — nothing else surfaces that.

Unauthenticated on purpose: the case this serves is a consumer wiring up
before it has a working key. Neither the names nor the `_dev`/`_test` suffix
rule is a secret — both are published in this repo — and the ports are
tailnet-only regardless.

`https://notifier.exe.xyz:9000/` reaches the exe.dev login gate and stops
there: nothing listens on the interface the proxy forwards to. Deliberate.

## The dead-man's-timer sweep

`notifier-sweep.timer` and `notifier-sweep-dev.timer` fire every 60 seconds
and are the only thing watching for consumer silence (#56). If a timer stops,
every dead-man's timer in the service stops with it and nothing says so.

```bash
systemctl list-timers 'notifier-sweep*'        # is it firing? when next?
systemctl --failed | grep notifier-sweep       # did a pass fail?
sudo systemctl start notifier-sweep.service    # force one pass now
```

The production sweep carries `NOTIFIER_ALLOW_PROD_DB=1` in its unit for the
same reason `notifier.service` does, and the dev sweep must never carry it:
inheriting it would have the dev endpoint's timer alerting on production
monitors and dispatching to production channels to do it.
`tests/deploy/test_sweep_units.py` asserts both.

Full reference: [reference/monitors.md](reference/monitors.md).

## The VM split (#43, done)

Notifier ran co-located on the `watcher` VM through v0, reached at
`http://localhost:9000`. #43 moved it here and replaced that hop with the
tailnet. The migration record — including the `pg_dump`/restore, the Fernet-key
verification gate, and the rollback path — is in that issue.

## The memory reservation (#74)

Measured on this host 2026-09-18: **3.8 GiB, no swap, 2 cores**, running the
live service, the dev endpoint, PostgreSQL *and* interactive agent sessions on
one kernel. Live peaks: `notifier.service` 90 MiB, `notifier-dev.service`
69 MiB, PostgreSQL 121 MiB. The agent sessions dwarf all three.

The failure this guards against is not an OOM kill — it is the **absence** of
one. Past the ceiling the kernel fails *atomic* allocations in whatever asks
next (`tailscaled`, `ksoftirqd`) and the production service is what goes down.
That is how `CannObserv/broker` lost its bus for 57m 48s on 2026-09-16 with
nothing killed at all (gregoryfoster/skills#295, `references/troubleshooting.md`
row U).

Four settings, none of which substitutes for another:

| Setting | Where | What it does |
|---|---|---|
| `MemoryLow=192M` | `deploy/notifier.service` | Soft floor the kernel will not reclaim below. Protects the working set, which is what a stall eats |
| `OOMScoreAdjust=-500` | `notifier.service`, `notifier-sweep.service` | Puts production last in line for the killer |
| `vm.min_free_kbytes=65536` | `deploy/99-notifier-memory.conf` | The reserve *atomic* allocations draw on. The two above are per-cgroup and cannot help `ksoftirqd` |
| `-m 12,6` + `--prefer`/`--avoid` | `deploy/earlyoom.default` | Acts while the host is still responsive; the kernel's own killer is too late on a no-swap host |

Three things are deliberate and easy to get wrong:

- **`MemoryLow=`, never `MemoryMax=`, on the service.** A cap bounds the
  victim rather than the cause, and on a process the killer will not pick it
  *stalls* instead of killing. The cap belongs on the SocratiCode pre-install
  below — a deliberate one-off run — never on the always-on service.
- **`-500`, never `-1000`.** Unkillable turns a leak in the service into a
  wedged host with no kill and no report.
- **The dev units carry none of it.** A reservation everything holds is a
  reservation nobody holds; under pressure dev is what loses, on purpose.

**No spaces inside the earlyoom regexes.** `earlyoom.service` is
`ExecStart=/usr/bin/earlyoom $EARLYOOM_ARGS`, unquoted, so systemd splits on
whitespace with no shell quoting — a space would silently become a second
argument, earlyoom would exit on it, and the host would be left with no early
killer and an `active`-looking unit. The SocratiCode server's `comm` is
literally `npm exec socrat`, so match it start-anchored as `^npm`.

`tests/deploy/test_memory_reservation.py` asserts all of it. Verify live:

```bash
systemctl show notifier -p MemoryLow -p OOMScoreAdjust
cat /proc/sys/vm/min_free_kbytes
tr '\0' '\n' < /proc/$(systemctl show earlyoom -p MainPID --value)/cmdline
```

### One divergence from broker worth knowing

Row U attributes half its severity to exe.dev session processes inheriting
`oom_score_adj` **-1000** from `exe-init` and `sshd`, which would make them
unkillable. **That does not hold here.** Measured on this host, only `sshd`
and `exe-init` themselves carry -1000; every `claude` and `npm exec socrat`
process sits at adj **0**. So the killer *can* pick them, and the
`OOMScoreAdjust=-500` above is what makes it prefer them over production.
Re-check with `cat /proc/<pid>/oom_score_adj` before assuming either shape.

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
