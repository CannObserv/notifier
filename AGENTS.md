# notifier — Agent Guidelines

Be terse. Prefer fragments over full sentences. Skip filler and preamble. Sacrifice grammar for density. Lead with the answer or action.

## Project Overview

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates + JSON-Schema variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; the service renders, validates, dispatches, and logs every attempt.

First consumer is the `watcher` project (Cannabis Observer). API is designed to be consumer-agnostic — no domain concepts leak into the service.

## Development Methodology

TDD required. Red → Green → Refactor. No production code without a failing test first.

## Environment & Tooling

Python ≥3.12, uv, pytest, ruff.

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

`/api/v1/` is versioned and auth-guarded; `/health` and `/ready` are root-level and unauthenticated. `clients/python/src/notifier_client/generated/` is generated from `/openapi.json` — never hand-edit it; CI fails a stale PR.

Per-module inventory: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Infrastructure

**Single-VM setup (shared with watcher).** This VM is both development and production. Code committed to main is the deployed code. The systemd service (`notifier`) runs the live service on port 9000.

| Service | Framework | Port | Managed by |
|---|---|---|---|
| API (live) | FastAPI | 9000 | `systemctl` (`notifier.service`) |
| API (dev) | FastAPI | 9001 | manual uvicorn |

The exe.dev proxy transparently forwards ports 3000–9999. Dev server on 9001 is accessible at `https://notifier.exe.xyz:9001/`.

Watcher (the first consumer) co-locates on this VM during v0; both services run side by side. Watcher's API on port 8000, notifier's on 9000.

## Server Lifecycle

**Port 9000 belongs to systemd.** Never start uvicorn manually on port 9000.

| Situation | Action |
|---|---|
| Code committed to main | `sudo systemctl restart notifier` |
| Testing a worktree/branch | `./scripts/dev_server.sh` (port 9001, dev DB) |
| Debugging the live service | `sudo journalctl -u notifier -f` |
| After editing `deploy/notifier.service` | `sudo systemctl daemon-reload && sudo systemctl restart notifier` |
| After DB model changes | `uv run alembic upgrade head` then restart |

**Dev server workflow:** Use the launch script. It loads secrets, swaps
`DATABASE_URL` for `DEV_DATABASE_URL`, runs the production-database guard, and
only then starts uvicorn on 9001 so the live service stays up:

```bash
./scripts/dev_server.sh
```

Never hand-run uvicorn. The old recipe sourced `/etc/notifier/.env` — which
sets `DATABASE_URL` to **production** — so the "dev" server on 9001 shared one
database with the live service on 9000 (issue #22). `src/core/db_safety.py`
now refuses any database whose name does not end in `_test` or `_dev`; the
production opt-in `NOTIFIER_ALLOW_PROD_DB=1` lives in the systemd unit and
must never be added to an env file.

**After finishing work:** Always restart the systemd service to pick up changes merged to main:

```bash
sudo systemctl restart notifier
```

## Environment Variables

Two env files, loaded in order (later values override):

1. **`/etc/notifier/.env`** — production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`). Survives repo resets and worktree switches. Managed manually on the VM.
2. **`.env`** (repo root, git-ignored) — dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`, `DEV_DATABASE_URL`). Never commit.

The systemd service loads both automatically. For shell commands, source them
— do not word-split them through `xargs`, which corrupts any value containing
spaces or quotes:

```bash
set -a; . /etc/notifier/.env; [ -r .env ] && . .env; set +a
```

**This leaves `DATABASE_URL` pointing at production.** That is correct for
`alembic upgrade head` and for `systemctl`, and wrong for everything else. Use
`./scripts/dev_server.sh` for a server; `pytest` pins `DATABASE_URL` to the
test database itself.

Currently defined:
- `DATABASE_URL` — PostgreSQL connection string (in `/etc/notifier/.env`)
- `PROCRASTINATE_DATABASE_URL` — (optional) libpq-style DSN for procrastinate; reserved for future async dispatch worker
- `GH_TOKEN` — GitHub personal access token (in `.env`)
- `TEST_DATABASE_URL` — PostgreSQL connection string for the test database `notifier_test` (in `.env`); `tests/conftest.py` pins `DATABASE_URL` to it for the whole session
- `DEV_DATABASE_URL` — PostgreSQL connection string for the dev database `notifier_dev` (in `.env`); `scripts/dev_server.sh` requires it
- `DEV_TENANT_API_KEY` — API key for the `dev` tenant in `notifier_dev` (in `.env`); marked `development`, so production refuses it
- `NOTIFIER_ALLOW_PROD_DB` — set to `1` **in `deploy/notifier.service` only** to let a process open the production database; see `src/core/db_safety.py`
- `BUILD_ID` — (optional) git SHA for observability; defaults to `"dev"`
- `NOTIFIER_SECRET_KEY` — Fernet key for encrypting Apprise URLs at rest (in `/etc/notifier/.env`); generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

## Common Commands

```bash
# Install dependencies
uv sync

# Load environment (required before migrations or gh). Leaves DATABASE_URL
# pointing at production — intended for alembic and systemctl, nothing else.
set -a; . /etc/notifier/.env; [ -r .env ] && . .env; set +a

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

# FastAPI dev server (port 9001, dev DB, guarded — never hand-run uvicorn)
./scripts/dev_server.sh
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
- **Do** validate `variables` against the template's `variables_schema` on dispatch. Reject 422 with a clear field path on miss.
- **Do** render with `StrictUndefined` so unbound references fail loudly rather than silently producing empty output.
- **Do** require `idempotency_key` to be tenant-scoped and unique-where-not-null; replay must be safe.
- **Do** mark every API key with an `environment` (`production` | `development`). A production deployment refuses `development` keys with 403. This is the only layer that sees a consumer's dev process calling production over HTTP — a database guard cannot (issue #22).

## Detail Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — per-module inventory: what every tracked directory and significant file is responsible for, including `tests/`, `deploy/`, and the skill trees
- [docs/COMMANDS.md](docs/COMMANDS.md) — every runnable command with flags: setup, migrations, test tiers, lint gates, SDK regeneration, tenant provisioning
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — first-time VM setup, systemd unit install, routine restart/migrate ops
- [docs/SOCRATICODE.md](docs/SOCRATICODE.md) — full SocratiCode tool table, the `ToolSearch` prefetch query, per-tool notes, graph-health guidance, and this repo's measured yield
- [docs/SKILLS.md](docs/SKILLS.md) — skill directory layout, vendored submodule repos and refresh procedure, full skills inventory
