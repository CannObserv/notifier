# Architecture

Module inventory for the notifier service. The boundaries that matter — and why
they exist — are summarised in [AGENTS.md](../AGENTS.md#project-layout); this file
is the enumeration behind them.

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
src/core/database.py         — Async engine + session factory; reads DATABASE_URL and hands it to db_safety before returning it
src/core/db_safety.py        — Production-database guard, plus `serving_production()` which classifies the running process for the API-key environment check in `src/api/deps.py`. `assert_safe_database_url` refuses any database whose name does not end in `_test`/`_dev` unless `NOTIFIER_ALLOW_PROD_DB=1`. Called from `get_database_url()`, the one chokepoint every connection path crosses. `alembic/env.py` is deliberately exempt (it reads os.environ directly); `python -m src.core.db_safety` is the CLI form used by `scripts/dev_server.sh`
src/core/logging.py          — `build_json_formatter()` (single formatter definition: `{timestamp, level, logger, message}`) + `ColorMessageFilter` (strips uvicorn's ANSI `color_message` extra) + `configure_logging()` (entry points only) + `get_logger(__name__)`
src/core/log_config.json     — uvicorn dictConfig passed via `--log-config`; routes `uvicorn`/`uvicorn.access`/`uvicorn.error` through `build_json_formatter` so uvicorn lines and app logs share one JSON schema
src/core/utils.py            — `format_utc_iso(dt)` ISO 8601 with Z suffix
src/core/crypto.py           — Fernet encryption for Apprise URLs at rest; requires `NOTIFIER_SECRET_KEY` env var; `encrypt_apprise_url` / `decrypt_apprise_url`
src/core/notifications/      — Apprise dispatch path + plugin catalog + Jinja rendering
src/core/notifications/dispatcher.py    — `dispatch_to_channel(*, apprise_url_encrypted, title, body, notify_type)`; per-channel format negotiation (HTML-native plugins like `mailto://` get a Markdown→HTML rewrite via `markdown_to_email_html`; others receive raw Markdown unchanged); ContextVar-isolated Apprise WARNING capture; AppriseAsset branding via `_ASSET`
src/core/notifications/apprise_builder.py — Plugin catalog introspection + URL assembly: `list_plugins()`, `get_plugin_detail(schema)`, `assemble_url(schema, tokens, variant_index)`; `_build_catalog()` and `_list_plugins_cached()` are `lru_cache`d
src/core/notifications/render.py        — Jinja2 strict rendering: `render_template(s, variables)` (StrictUndefined; raises on syntax + undefined refs)
src/core/notifications/validate.py      — JSON Schema variables validation against template schema; raises a typed VariablesValidationError with field path
src/core/notifications/html_render.py   — Markdown→HTML pipeline (mistune) for HTML-native channels; `markdown_to_email_html(body)` runs source through a custom `_DiffAwareRenderer` that styles ```diff fenced blocks with the GitHub palette via inline CSS; pure functions, no I/O
src/core/notifications/constants.py     — `APP_URL_ENV_VAR` (`NOTIFIER_APP_URL`, read by `dispatcher._build_asset()`; unset ships no branding link at all); `DispatchStatus` + `DispatchAttemptStatus` StrEnums (canonical server-side status values used in dispatch route and cross-checked against Pydantic schema Literals)
tests/                       — Mirrors src/ structure; integration tests use real Postgres via TEST_DATABASE_URL. `tests/conftest.py` pins `DATABASE_URL` to `TEST_DATABASE_URL` at module level so a shell that sourced production secrets cannot leak them into a test run
tests/deploy/                — Drift tests for the deploy surface: `scripts/dev_server.sh` (guard delegation, safe env loading, port 9001, refusal paths, the `NOTIFIER_DEV_RELOAD` toggle exercised through a fake-`uv` PATH shim, and that no doc has regrown the unguarded recipe), `deploy/notifier.service` (the opt-in flag is in the unit and in no env file), and `deploy/notifier-dev.service` (the opt-in flag is *absent*, ExecStart is the guarded script rather than a uvicorn line, reloader off, restarts bounded)
clients/python/              — `notifier-client` Python SDK; separate `pyproject.toml` + venv (`uv sync` from this dir); `src/notifier_client/generated/` is regenerated from `/openapi.json` via `clients/python/scripts/regen.sh` and must never be hand-edited; CI fails any PR that leaves it stale. Public types in `notifier_client.types`; sub-clients under `client.channels`, `client.templates`, `client.apprise`.
deploy/                      — Systemd units: `notifier.service` (production, :9000, carries `NOTIFIER_ALLOW_PROD_DB=1`) and `notifier-dev.service` (dev endpoint, :9001, `notifier_dev`, runs `scripts/dev_server.sh` with the reloader off and no production opt-in — the base URL consumers point non-production processes at, #24)
docs/                        — Reference docs (COMMANDS, DEPLOYMENT, SKILLS, SOCRATICODE); `docs/plans/` holds implementation plans
scripts/                     — Helper scripts: `load_env.sh` (source it — the one env-loading recipe, resolves the repo `.env` from its own location so it works from any cwd), `dev_server.sh` (the only supported dev-server launch, used both by hand and as `notifier-dev.service`'s ExecStart — loads secrets, swaps in `DEV_DATABASE_URL`, runs the guard, checks migration state, then uvicorn on 9001; `NOTIFIER_DEV_RELOAD=0` drops `--reload` for the unit), `seed_tenant.py` (provision tenant + API key; production requires the opt-in flag), `dump_openapi.py` (dump app.openapi() JSON for SDK regen)
skills/                      — Agent skills: committed local overrides + symlinks → skills-vendor/
skills-vendor/               — Git submodules for external skill repos (gregoryfoster-skills, obra-superpowers)
.claude/skills/              — Claude Code skill discovery: symlinks → ../../skills/<name>
.socraticodecontextartifacts.json — SocratiCode context artifacts catalog (DB schema, deployment, runbook, systemd unit) for semantic search beyond raw code
```

The current reference-doc index is [AGENTS.md § Detail Docs](../AGENTS.md#detail-docs);
the `docs/` entry above predates this file.

**Environment files** (not in the repo tree):
- `/etc/notifier/.env` — Production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`); outside repo, persistent. Sourcing it leaves `DATABASE_URL` on **production** — intended for alembic and systemctl only
- `.env` (repo root) — Dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`); git-ignored
