# notifier — Agent Guidelines

Be terse. Prefer fragments over full sentences. Skip filler and preamble. Sacrifice grammar for density. Lead with the answer or action.

## Project Overview

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates + JSON-Schema variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; the service renders, validates, dispatches, and logs every attempt.

First consumer is the `watcher` project (Cannabis Observer). API is designed to be consumer-agnostic — no domain concepts leak into the service.

## Development Methodology

TDD required. Red → Green → Refactor. No production code without a failing test first.

## Environment & Tooling

Python ≥3.12, uv, pytest, ruff.

## Code Exploration Policy

SocratiCode is indexed on this repo (`.socraticodecontextartifacts.json` present). Its MCP tools are **deferred** — schemas load only after a `ToolSearch` prefetch. The SessionStart hook prints the prefetch query; run it before exploring.

**Negative rule.** For broad semantic questions ("where is X", "how does Y work", "what depends on Z"), use SocratiCode MCP tools first. Reach for `grep`/`ripgrep` only on exact strings (error messages, log lines, known symbols). Reserve the Explore subagent for path-pattern walks (e.g. "all `*.py` under `src/api/routes/`"), not semantic search.

| Goal | Tool |
|------|------|
| Where is X defined / how does Y work / what files touch Z | `codebase_search` |
| Exact string/regex match (errors, log lines, known symbols) | `grep` / `rg` |
| Blast radius of changing/deleting a file or function | `codebase_impact` |
| What does an entry point actually do? | `codebase_flow` |
| Callers and callees of a function | `codebase_symbol` |
| Imports/dependents of a file | `codebase_graph_query` |
| DB schemas, deployment topology, runbook context | `codebase_context` / `codebase_context_search` |

Prefetch query — run via `ToolSearch` at session start:

`select:mcp__plugin_socraticode_socraticode__codebase_search,mcp__plugin_socraticode_socraticode__codebase_symbol,mcp__plugin_socraticode_socraticode__codebase_symbols,mcp__plugin_socraticode_socraticode__codebase_flow,mcp__plugin_socraticode_socraticode__codebase_impact,mcp__plugin_socraticode_socraticode__codebase_graph_query,mcp__plugin_socraticode_socraticode__codebase_graph_circular,mcp__plugin_socraticode_socraticode__codebase_graph_stats,mcp__plugin_socraticode_socraticode__codebase_graph_visualize,mcp__plugin_socraticode_socraticode__codebase_status,mcp__plugin_socraticode_socraticode__codebase_context,mcp__plugin_socraticode_socraticode__codebase_context_search`

## Project Layout

```
src/api/                     — FastAPI app (ASGI, routes, schemas); /api/v1/ versioned + auth-guarded; /health, /ready root-level
src/api/routes/templates.py  — CRUD + preview for templates; `POST /templates/{id}/preview` renders with `sample_variables` or supplied variables
src/api/routes/channels.py   — CRUD + test for channels; Apprise URL encrypted at rest; never returned in plaintext
src/api/routes/dispatch.py   — `POST /dispatch` (renders, validates, dispatches, logs); `GET /dispatch/{id}`; `GET /dispatch?event_type=&since=&limit=` log query
src/api/routes/preview.py    — Stateless `POST /preview` that takes inline templates + variables, returns rendered title/body or per-section error
src/api/routes/apprise_plugins.py — `GET /apprise/plugins`, `GET /apprise/plugins/{schema}`, `POST /apprise/plugins/{schema}/assemble`
src/api/routes/health.py     — `/health` (liveness) and `/ready` (DB) — root-level, not versioned
src/api/deps.py              — FastAPI deps: `get_db_session`, `require_api_key` (X-API-Key → tenant_id as `str`; 403 absent, 401 invalid)
src/api/schemas/types.py     — Shared Pydantic field types: `ULIDStr` (26-char Crockford base32, normalised to uppercase; use on all `*_id` path params and request-body ID fields; invalid input → 422 with field path)
src/core/                    — Shared domain logic
src/core/models/             — SQLAlchemy models: Tenant, ApiKey [hashed; key_hash=SHA-256, key_prefix=first 8 chars], Channel [apprise_url encrypted], Template [title_template, body_template, variables_schema JSONB, sample_variables JSONB, tags ARRAY], Dispatch [variables JSONB, metadata JSONB, status, idempotency_key (unique with tenant_id)], DispatchAttempt [keyed by (dispatch_id, channel_id), attempt int, status, reason]
src/core/database.py         — Async engine + session factory; reads DATABASE_URL
src/core/logging.py          — `configure_logging()` (entry points only) + `get_logger(__name__)`
src/core/utils.py            — `format_utc_iso(dt)` ISO 8601 with Z suffix
src/core/crypto.py           — Fernet encryption for Apprise URLs at rest; requires `NOTIFIER_SECRET_KEY` env var; `encrypt_apprise_url` / `decrypt_apprise_url`
src/core/notifications/      — Apprise dispatch path + plugin catalog + Jinja rendering
src/core/notifications/dispatcher.py    — `dispatch_to_channel(*, apprise_url_encrypted, title, body, notify_type)`; ContextVar-isolated Apprise WARNING capture; AppriseAsset branding via `_ASSET`
src/core/notifications/apprise_builder.py — Plugin catalog introspection + URL assembly: `list_plugins()`, `get_plugin_detail(schema)`, `assemble_url(schema, tokens, variant_index)`; `_build_catalog()` and `_list_plugins_cached()` are `lru_cache`d
src/core/notifications/render.py        — Jinja2 strict rendering: `render_template(s, variables)` (StrictUndefined; raises on syntax + undefined refs)
src/core/notifications/validate.py      — JSON Schema variables validation against template schema; raises a typed VariablesValidationError with field path
src/core/notifications/constants.py     — `APP_URL` ("https://notifier.exe.xyz") used by AppriseAsset branding; `DispatchStatus` + `DispatchAttemptStatus` StrEnums (canonical server-side status values used in dispatch route and cross-checked against Pydantic schema Literals)
tests/                       — Mirrors src/ structure; integration tests use real Postgres via TEST_DATABASE_URL
clients/python/              — `notifier-client` Python SDK; separate `pyproject.toml` + venv (`uv sync` from this dir); `src/notifier_client/generated/` is regenerated from `/openapi.json` via `clients/python/scripts/regen.sh` and must never be hand-edited; CI fails any PR that leaves it stale. Public types in `notifier_client.types`; sub-clients under `client.channels`, `client.templates`, `client.apprise`.
deploy/                      — Systemd unit + deployment config
docs/                        — Reference docs (COMMANDS, DEPLOYMENT, SKILLS); `docs/plans/` holds implementation plans
scripts/                     — Helper scripts: `seed_tenant.py` (provision tenant + API key), `dump_openapi.py` (dump app.openapi() JSON for SDK regen)
skills/                      — Agent skills: committed local overrides + symlinks → skills-vendor/
skills-vendor/               — Git submodules for external skill repos (gregoryfoster-skills, obra-superpowers)
.claude/skills/              — Claude Code skill discovery: symlinks → ../../skills/<name>
.socraticodecontextartifacts.json — SocratiCode context artifacts catalog (DB schema, deployment, runbook, systemd unit) for semantic search beyond raw code
```

**Environment files** (not in the repo tree):
- `/etc/notifier/.env` — Production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`); outside repo, persistent
- `.env` (repo root) — Dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`); git-ignored

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
| Testing a worktree/branch | `uv run uvicorn ... --port 9001 --reload` |
| Debugging the live service | `sudo journalctl -u notifier -f` |
| After editing `deploy/notifier.service` | `sudo systemctl daemon-reload && sudo systemctl restart notifier` |
| After DB model changes | `uv run alembic upgrade head` then restart |

**Dev server workflow:** Run on port 9001 so the live service stays up. Load env first:

```bash
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 9001 --reload
```

**After finishing work:** Always restart the systemd service to pick up changes merged to main:

```bash
sudo systemctl restart notifier
```

## Environment Variables

Two env files, loaded in order (later values override):

1. **`/etc/notifier/.env`** — production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`). Survives repo resets and worktree switches. Managed manually on the VM.
2. **`.env`** (repo root, git-ignored) — dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`). Never commit.

The systemd service loads both automatically. For shell commands:

```bash
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
```

Currently defined:
- `DATABASE_URL` — PostgreSQL connection string (in `/etc/notifier/.env`)
- `PROCRASTINATE_DATABASE_URL` — (optional) libpq-style DSN for procrastinate; reserved for future async dispatch worker
- `GH_TOKEN` — GitHub personal access token (in `.env`)
- `TEST_DATABASE_URL` — PostgreSQL connection string for test database (in `.env`)
- `BUILD_ID` — (optional) git SHA for observability; defaults to `"dev"`
- `NOTIFIER_SECRET_KEY` — Fernet key for encrypting Apprise URLs at rest (in `/etc/notifier/.env`); generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

## Common Commands

```bash
# Install dependencies
uv sync

# Load environment (required before running server, migrations, or gh)
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)

# Run tests
uv run pytest

# Run integration tests (requires PostgreSQL)
uv run pytest -m integration

# Run linter
uv run ruff check .

# Database migrations
uv run alembic upgrade head          # apply all migrations
uv run alembic revision --autogenerate -m "description"  # generate new migration

# FastAPI dev server (port 9001 — port 9000 belongs to systemd)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 9001 --reload
```

Full reference: `docs/COMMANDS.md`

## Agent Skills

Skills in `skills/` (agentskills.io) and `.claude/skills/` (Claude Code). Reference: `docs/SKILLS.md`

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
