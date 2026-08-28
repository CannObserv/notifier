# notifier — Agent Guidelines

Be terse. Prefer fragments over full sentences. Skip filler and preamble. Sacrifice grammar for density. Lead with the answer or action.

## Project Overview

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates + JSON-Schema variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; the service renders, validates, dispatches, and logs every attempt.

First consumer is the `watcher` project (Cannabis Observer). API is designed to be consumer-agnostic — no domain concepts leak into the service.

## Development Methodology

TDD required. Red → Green → Refactor. No production code without a failing test first.

## Environment & Tooling

Python ≥3.12, uv, pytest, ruff.

## Continuous Integration

`.github/workflows/ci.yml` runs `lint`, `test`, and `migrations` on every push
to main, on PRs, and on manual dispatch. `sdk-staleness.yml` runs on the same
triggers when `src/api/**`, `scripts/dump_openapi.py`, or `clients/python/**`
changes.

Two things not to re-derive from the YAML:

- **`pre-commit` runs ruff only, never pytest.** A clean commit hook says
  nothing about correctness — only CI does.
- **CI pins CPython 3.12 and installs with `uv sync --locked`, deliberately.**
  `[tool.coverage.run] core = "sysmon"` needs ≥3.12 and coverage ≥7.10; below
  either it falls back silently and reports ~6 points low against the live
  `fail_under = 80`. `tests/ci/` asserts both, so a runner change fails loudly.

<!-- BEGIN socraticode-policy -->
## Code Exploration Policy

SocratiCode is the preferred semantic-search tool here once indexed (local
Qdrant store + on-disk graph; manifest `.socraticodecontextartifacts.json`).
Its MCP tools are **deferred** — schemas load only after the `ToolSearch`
prefetch that `.claude/hooks/socraticode-reminder.sh` prints each session.

**Negative rule.** Use SocratiCode MCP tools first for semantic questions
("where is X", "how does Y work", "what depends on Z"). Reach for `grep`/`rg`
only on exact strings (error messages, log lines, known symbols). Reserve the
Explore subagent for path-pattern walks (`*.py` under `src/api/routes/`), not
semantic search.

| Goal | Tool |
|------|------|
| Where is X defined / how does Y work / what touches Z | `codebase_search` |
| Exact string or regex (errors, log lines, known symbols) | `grep` / `rg` |
| Imports/dependents of a file · blast radius of a change | `codebase_graph_query` / `codebase_impact` |

Full tool table, prefetch query, per-tool guidance: [`docs/SOCRATICODE.md`](docs/SOCRATICODE.md).
<!-- END socraticode-policy -->

## Project Layout

Two packages, one boundary: `src/api/` is transport (routes, Pydantic schemas, auth deps) and `src/core/` is domain logic (models, crypto, Apprise dispatch, Jinja rendering). Core never imports api.

`/api/v1/` is versioned and auth-guarded; `/health` and `/ready` are root-level and unauthenticated. `clients/python/src/notifier_client/generated/` is generated from `/openapi.json` — never hand-edit it; `sdk-staleness.yml` fails a stale push to main or PR.

Per-module inventory: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Infrastructure

**Own VM since #43.** `notifier.exe.xyz` (exe.dev, `pdx`) runs this service and
its PostgreSQL 16 cluster, nothing else. Dev and production both. Code
committed to main is the deployed code; `notifier.service` runs the live
service on port 9000.

| Service | Framework | Port | Managed by |
|---|---|---|---|
| API (live) | FastAPI | 9000 | `systemctl` (`notifier.service`), production DB |
| API (dev) | FastAPI | 9001 | `systemctl` (`notifier-dev.service`), `notifier_dev` |

Both always-on. **9001 is the development endpoint consumers point at** — it
accepts `development`-marked API keys, which 9000 refuses (#24).
`./scripts/dev_server.sh` still runs a worktree or branch by hand; stop the dev
unit first so the two do not fight over the port.

**Both bind this host's tailnet address alone, never `0.0.0.0`.** Unreachable
from exe.dev's internal `10.42.0.0/16`, from the exe.dev proxy, and from the
internet — the Tailscale ACL decides who gets in. Address resolved by
`scripts/tailnet_bind.sh`, which waits for tailscaled and fails loudly rather
than falling back to a wider bind. Full reference:
[docs/reference/tailscale.md](docs/reference/tailscale.md).

Reachable by MagicDNS from any node on the `cannobserv.org.github` tailnet:

| From | Live | Dev |
|---|---|---|
| Another tailnet node | `http://notifier:9000` | `http://notifier:9001` |
| **This VM itself** | `http://$(tailscale ip -4):9000` | same, `:9001` |

**On this VM both `127.0.0.1:9000` and `http://notifier:9000` fail** — Ubuntu's
`/etc/hosts` maps the hostname `notifier` to `127.0.1.1`, which nothing binds.
Use the tailnet address:

```bash
curl "http://$(tailscale ip -4):9000/health"
```

`https://notifier.exe.xyz:9000/` reaches the exe.dev login gate and stops:
nothing listens on the interface the proxy forwards to. Deliberate, not broken.

Watcher, the first consumer, is on the separate `watcher` VM (`lax`) with
archiver and replicator; its API is on 8000 there. Its production credential
lives in `/etc/watcher/notifier.env` on that host, pointed at
`http://notifier:9000` (watcher#278).

## Server Lifecycle

**Port 9000 belongs to systemd.** Never start uvicorn manually on port 9000.

| Situation | Action |
|---|---|
| Code committed to main | `sudo systemctl restart notifier notifier-dev` |
| Testing a worktree/branch | `sudo systemctl stop notifier-dev` then `./scripts/dev_server.sh` |
| Debugging the live service | `sudo journalctl -u notifier -f` |
| Debugging the dev endpoint | `sudo journalctl -u notifier-dev -f` |
| After editing either unit in `deploy/` | `sudo systemctl daemon-reload && sudo systemctl restart notifier notifier-dev` |
| After DB model changes | `uv run alembic upgrade head`, then the same against `DEV_DATABASE_URL`, then restart both |

**Dev server workflow:** One launch path serves both the unit and the hand-run
case. `scripts/dev_server.sh` loads secrets, swaps `DATABASE_URL` for
`DEV_DATABASE_URL`, runs the production-database guard, checks the dev
database is migrated, and only then starts uvicorn on 9001 so the live service
stays up:

```bash
sudo systemctl stop notifier-dev   # the unit owns 9001; take it first
./scripts/dev_server.sh            # foreground, --reload on
sudo systemctl start notifier-dev  # hand it back
```

`deploy/notifier-dev.service` runs that same script with
`NOTIFIER_DEV_RELOAD=0`. Under systemd the reloader is wrong twice over: an
edit mid-request drops a consumer's connection, and a syntax error on `main`
leaves the reloader wedged and *running*, so `Restart=on-failure` never fires
and the endpoint is silently dead.

Never hand-run uvicorn. The old recipe sourced `/etc/notifier/.env` — which
sets `DATABASE_URL` to **production** — so the "dev" server on 9001 shared one
database with the live service on 9000 (issue #22). Still true on a dedicated
VM: the two endpoints share a host and a cluster, only the database differs. `src/core/db_safety.py`
now refuses any database whose name does not end in `_test` or `_dev`; the
production opt-in `NOTIFIER_ALLOW_PROD_DB=1` lives in the systemd unit and
must never be added to an env file.

**After finishing work:** Always restart both services to pick up changes merged to main — they serve one working tree, so restarting only the live one leaves the dev endpoint answering from stale code:

```bash
sudo systemctl restart notifier notifier-dev
```

## Environment Variables

Two env files, loaded in order (later values override):

1. **`/etc/notifier/.env`** — production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`). Survives repo resets and worktree switches. Managed manually on the VM.
2. **`.env`** (repo root, git-ignored) — dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`, `DEV_DATABASE_URL`). Never commit.

The systemd service loads both automatically. For shell commands, source them
— do not word-split them through `xargs`, which corrupts any value containing
spaces or quotes:

```bash
. scripts/load_env.sh
```

**This leaves `DATABASE_URL` pointing at production.** That is correct for
`alembic upgrade head` and for `systemctl`, and wrong for everything else. Use
`./scripts/dev_server.sh` for a server; `pytest` pins `DATABASE_URL` to the
test database itself.

Currently defined:
- `DATABASE_URL` — PostgreSQL connection string (in `/etc/notifier/.env`)
- `GH_TOKEN` — GitHub personal access token (in `.env`)
- `TEST_DATABASE_URL` — PostgreSQL connection string for the test database `notifier_test` (in `.env`); `tests/conftest.py` pins `DATABASE_URL` to it for the whole session
- `DEV_DATABASE_URL` — PostgreSQL connection string for the dev database `notifier_dev` (in `.env`); `scripts/dev_server.sh` requires it, so `notifier-dev.service` does too
- `NOTIFIER_DEV_RELOAD` — `0` disables uvicorn's reloader in `scripts/dev_server.sh`; set in `deploy/notifier-dev.service` only, defaults to on for a hand-run server
- `DEV_TENANT_API_KEY` — API key for the `dev` tenant in `notifier_dev` (in `.env`); marked `development`, so production refuses it
- `NOTIFIER_ALLOW_PROD_DB` — set to `1` **in `deploy/notifier.service` only** to let a process open the production database; see `src/core/db_safety.py`
- `BUILD_ID` — (optional) git SHA reported by `/health`; blank or unset both fall back to `"dev"`. Each systemd unit stamps its own file (`/run/notifier/build-id`, `/run/notifier/build-id-dev`) from `git rev-parse` at start
- `NOTIFIER_APP_URL` — (optional) branding URL embedded in delivered notifications. Unset means **no link**, which is the default: six Apprise plugins render it as a clickable link, and Apprise's own fallback is the Apprise GitHub repo. Set it only to an address that actually resolves. **Read once at import**, so a change needs a service restart before it takes effect
- `NOTIFIER_SECRET_KEY` — Fernet key for encrypting Apprise URLs at rest (in `/etc/notifier/.env`); `scripts/dev_server.sh` refuses to start without it, because a server that lacks it still answers `/ready` and fails only at the first dispatch; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
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

## Common Commands

```bash
# Install dependencies
uv sync

# Load environment (required before migrations or gh). Leaves DATABASE_URL
# pointing at production — intended for alembic and systemctl, nothing else.
. scripts/load_env.sh

# Run tests
uv run pytest

# Run a subset of tests (skip the coverage gate, which measures all of src/)
uv run pytest --no-cov tests/core/test_utils.py

# Run integration tests (requires PostgreSQL)
uv run pytest -m integration

# Run linter
uv run ruff check .

# Format (both gates below run at ship/review time — `--check` is the gate)
uv run ruff format .
uv run ruff format --check .

# Run every gate the way pre-commit does
uv run pre-commit run --all-files
uv run pre-commit install            # once per clone — installs it as a git hook

# Database migrations
uv run alembic upgrade head          # apply all migrations
uv run alembic revision --autogenerate -m "description"  # generate new migration

# FastAPI dev server by hand (port 9001, dev DB, guarded — never hand-run
# uvicorn). Stop notifier-dev.service first; it holds the port.
sudo systemctl stop notifier-dev && ./scripts/dev_server.sh
```

Full reference: `docs/COMMANDS.md`

## Agent Skills

Skills in `skills/` (agentskills.io) and `.claude/skills/` (Claude Code). Reference: `docs/SKILLS.md`

Vendored skills plus local overrides in `skills/` that shadow the vendor copy. Inventory, sources, and override notes: [§ Skills Inventory](docs/SKILLS.md#skills-inventory).

## Conventions

**Commit Messages:**
```
#<number> [type]: <description>      # with issue
[type]: <description>                # without issue
```
Types: feat, fix, refactor, docs, test, chore

**Logging:**
```python
from src.core.logging import get_logger
logger = get_logger(__name__)
```
Entry points only: call `configure_logging()` once.

**Date & Time:**
- All UTC
- ISO 8601: `YYYY-MM-DDTHH:MM:SS.ffffffZ` (timestamps), `YYYY-MM-DD` (dates)

**Dependencies:** four rules, all asserted by `tests/ci/test_dependencies.py` — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#dependency-policy) before adding or bumping one

**General:**
- No inline module imports; all at file top
- Docstrings for public modules, classes, functions
- Test structure mirrors source (`src/foo.py` → `tests/test_foo.py`)
- Explicit imports only
- Small, focused functions

## API Boundary Principles

The service is consumer-agnostic. Resist these temptations:

- **Do not** introduce a top-level `event_type` field on dispatch — that's consumer taxonomy. Consumers put it in `metadata` if they want it indexed.
- **Do not** infer routing/subscriptions in v0 — consumers pass `channel_ids` explicitly. Subscription model is v1.
- **Do not** fetch consumer data (no diff loading, no snapshot reads). Consumers ship rendered or pre-rendered values via `variables`.
- **Do not** branch on tenant identity inside business logic. Tenancy is enforced at the auth layer; the rest of the code treats `tenant_id` as a partition key.
- **Do** validate `variables` against the template's `variables_schema` on dispatch. Reject 422 with a clear field path on miss. The *schema itself* is checked twice: on template write, where a malformed one is a 422 naming `body.variables_schema`, and again at dispatch, which is what catches rows stored before that guard landed (#28).
- **Do** render with `StrictUndefined` so unbound references fail loudly rather than silently producing empty output.
- **Do** require `idempotency_key` to be tenant-scoped and unique-where-not-null; replay must be safe.
- **Do** mark every API key with an `environment` (`production` | `development`). A production deployment refuses `development` keys with 403. This is the only layer that sees a consumer's dev process calling production over HTTP — a database guard cannot (issue #22).

## Detail Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — per-module inventory: what every tracked directory and significant file is responsible for, including `tests/`, `deploy/`, and the skill trees; plus the dependency policy every specifier is held to
- [docs/COMMANDS.md](docs/COMMANDS.md) — every runnable command with flags: setup, migrations, test tiers, lint gates, SDK regeneration, tenant provisioning
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — first-time VM setup, systemd unit install, routine restart/migrate ops
- [docs/reference/tailscale.md](docs/reference/tailscale.md) — the tailnet this VM lives on: node identity, ACL, the bind decision and the boot race it buys, and how to re-join or move the host
- [docs/SOCRATICODE.md](docs/SOCRATICODE.md) — full SocratiCode tool table, the `ToolSearch` prefetch query, per-tool notes, graph-health guidance, and this repo's measured yield
- [docs/SKILLS.md](docs/SKILLS.md) — skill directory layout, vendored submodule repos and refresh procedure, full skills inventory
