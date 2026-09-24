# Architecture

Module inventory for the notifier service. The boundaries that matter — and why
they exist — are summarised in [AGENTS.md](../AGENTS.md#project-layout); this file
is the enumeration behind them.

## Project Layout

The `tests/` entries below name what each directory covers; the
assertion-by-assertion enumeration behind them is in
[reference/drift-tests.md](reference/drift-tests.md).
Two more annexes carry what outgrew the block: what the notable tests under
`tests/api/` and `tests/core/`, the script tests and the conftest fixtures
pin, in [reference/test-inventory.md](reference/test-inventory.md), and the
per-script inventory of `scripts/` in
[reference/scripts.md](reference/scripts.md).

```
src/api/                     — FastAPI app (ASGI, routes, schemas); /api/v1/ versioned + auth-guarded; /health, /ready root-level
src/api/routes/templates.py  — CRUD + preview for templates; `POST /templates/{id}/preview` renders with `sample_variables` or supplied variables. Write paths reject a malformed `variables_schema` with a 422 naming `body.variables_schema` (via `JSONSchemaDict`), and a `sample_variables` bag the *merged* `variables_schema` refuses — PATCH judges a lone field against the stored sibling — with a 422 `{section: "sample_variables"}` (#31); preview reports a bad *stored* schema in-band as `error_section: "variables_schema"` rather than raising
src/api/routes/channels.py   — CRUD + test for channels; Apprise URL encrypted at rest; never returned in plaintext
src/api/routes/dispatch.py   — `POST /dispatch` (renders, validates, dispatches, logs); `GET /dispatch/{id}`; `GET /dispatch?event_type=&since=&limit=` log query
src/api/routes/monitors.py   — Monitor CRUD + `POST /monitors/{id}/checkin`: the dead-man's timer's front door (#56). A check-in arrives every tick regardless of findings — its *arrival* resets the timer, and its two-valued `status` says whether the contents also warrant dispatching the monitor's template. Consumer-agnostic on purpose: `variables` is opaque, so a broker's `finding_count`/`findings` report passes through verbatim without that vocabulary entering the schema. A check-in that ends an outage also dispatches a recovery notice. Request/response models in `src/api/schemas/monitor.py`
src/api/routes/preview.py    — Stateless `POST /preview` that takes inline templates + variables, returns rendered title/body or per-section error
src/api/routes/apprise_plugins.py — `GET /apprise/plugins`, `GET /apprise/plugins/{schema}`, `POST /apprise/plugins/{schema}/assemble`
src/api/routes/health.py     — `/health` (liveness) and `/ready` (DB) — root-level, not versioned. `_resolve_build_id()` reports the serving commit, treating a blank `BUILD_ID` as unstamped: the units write it via `echo BUILD_ID=$(git rev-parse …)`, which succeeds with an empty value when git fails. `_resolve_database()` reports which deployment answered, because `build` cannot — one working tree means both ports report the same SHA (#58). It fails *soft* where `db_safety` fails closed (`unknown`/`production` on an unreadable URL): raising at import would mean the app never starts. `/health` reads the configured URL; `/ready` names the database actually connected, via `current_database()`, so the two disagreeing is itself the signal
src/api/deps.py              — FastAPI deps: `get_db_session`, `require_api_key` (X-API-Key → tenant_id as `str`; 403 absent, 401 invalid, 403 for a `development` key on a production deployment). The digest it looks a key up by comes from `src.core.api_keys.hash_key` — the same function that writes it, because two spellings of the hash is a credential that mints fine and cannot authenticate (#62)
src/api/schemas/health.py    — `HealthResponse`, `ReadyResponse`, `NotReadyResponse`. Typed rather than a bare `dict` because consumers are told to assert on `environment`, and an untyped route generates a free-form `additional_properties` bag in the SDK — a new key there is byte-identical to no change at all. Three models rather than two: one model spanning `/ready`'s 200 and its 503 would need `database`/`environment` optional, publishing them as nullable on the path where they are always present
src/api/schemas/types.py     — Shared Pydantic field types: `ULIDStr` (26-char Crockford base32, normalised to uppercase; use on all `*_id` path params and request-body ID fields; invalid input → 422 with field path) and `JSONSchemaDict` (a JSON Schema document checked against the 2020-12 metaschema on write; used by the template request models, deliberately not by preview, which reports errors in-band)
src/core/                    — Shared domain logic
src/core/models/             — SQLAlchemy models: Tenant, ApiKey [hashed; key_hash=SHA-256, key_prefix=first 8 chars], Channel [apprise_url encrypted], Template [title_template, body_template, variables_schema JSONB, sample_variables JSONB, tags ARRAY], Dispatch [variables JSONB, metadata JSONB, status, idempotency_key (unique with tenant_id)], DispatchAttempt [keyed by (dispatch_id, channel_id), attempt int, status, reason], Monitor [interval_seconds + grace_seconds define the deadline, channel_ids ARRAY, state pending|ok|missing, last_checkin_at, last_variables JSONB verbatim, renotify_seconds]
src/core/database.py         — Async engine + session factory; reads DATABASE_URL and hands it to db_safety before returning it
src/core/db_safety.py        — Production-database guard, plus two classifiers over one rule: `serving_production()` (bool, reads the environment) for the API-key check in `src/api/deps.py`, and `environment_label()` (name → `production`/`development`) which both health probes share so their *disagreement* stays a meaningful signal. `assert_safe_database_url` refuses any database whose name does not end in `_test`/`_dev` unless `NOTIFIER_ALLOW_PROD_DB=1`. Called from `get_database_url()`, the one chokepoint every connection path crosses. `alembic/env.py` is deliberately exempt (it reads os.environ directly); `python -m src.core.db_safety` is the CLI form used by `scripts/dev_server.sh`
src/core/logging.py          — `build_json_formatter()` (single formatter definition: `{timestamp, level, logger, message}`) + `ColorMessageFilter` (strips uvicorn's ANSI `color_message` extra) + `configure_logging(stream=stdout)` (entry points only) + `get_logger(__name__)`, plus the credential audit channel: `get_audit_logger()` (`notifier.audit`), `configure_audit_logging()` (a `SysLogHandler` on `/dev/log` tagged `notifier-keys`, `propagate=False` so records never reach the root handler's stream, degrading to stderr with a WARNING when the socket is unreachable rather than dropping silently), and `configure_script_logging()`, which the three credential scripts call so stdout stays the operator's alone (#67)
src/core/log_config.json     — uvicorn dictConfig passed via `--log-config`; routes `uvicorn`/`uvicorn.access`/`uvicorn.error` through `build_json_formatter` so uvicorn lines and app logs share one JSON schema
src/core/api_keys.py         — The one spelling of how a credential is made, hashed, and destroyed: `hash_key` (what `src/api/deps.py` looks a key up by), `generate_raw_key`, `mint`, `revoke`, `keys_for`, `key_count`, and `ulid_str`, which normalises a `ulid.ULID` column value and an operator's `str` argv to one form so the tenancy check does not lean on those comparing equal. Neither `mint` nor `revoke` commits — the caller owns the transaction, which is what puts both halves of a rotation in one. `revoke` is scoped by tenant *and* key, and refuses a tenant's last key unless forced — locking the tenant row `FOR UPDATE` first, so two revokes racing on one tenant cannot each count two keys and each delete one. Revocation is a DELETE and there is no `revoked_at`: a filter that must be remembered fails open, a missing row fails closed; the audit trail is a log line on every mint and revoke that never names the raw key (#62), emitted on the `notifier.audit` channel the credential scripts point at journald — it went to this module's own logger and was dropped before reaching any stream until #67. `revoke` is not the only path that destroys a key: `src/core/tenants.py` records the ones a tenant deletion cascades (#79)
src/core/channels.py         — `copy_channels`: give a tenant copies of another tenant's channels by copying the stored Fernet token **verbatim**, never decrypting it. That works because one server key encrypts every channel and a token carries no associated data binding it to its tenant. It removes the one onboarding step that put a live Apprise URL in a clipboard or a transcript, since the API only returns a masked URL. All or nothing: an unknown target or source, a copy into the owning tenant, or a name the target already has (names aren't unique in the schema, so a re-run would otherwise duplicate) all refuse before anything is written. It owns its transaction like `delete_tenant`: `dry_run` (the default) rolls back silently, and a real run commits and then emits one `channel copied` audit record per copy, naming both ends and never the URL
src/core/tenants.py          — Tenant deletion and the record it leaves (#79): `inventory_of` (read-only; keys as `KeyRecord` snapshots, the rest counted) and `delete_tenant`, which locks the tenant `FOR UPDATE`, reads that inventory, clears the tenant's `dispatch_attempts`, deletes, and emits one `api key destroyed with tenant` record per cascaded key plus a closing `tenant deleted` summary. The attempts cannot wait for the cascade — `dispatch_attempts.channel_id` is `ON DELETE RESTRICT`, so a bare `DELETE FROM tenants` fails for any tenant that has ever dispatched. Unlike `mint`/`revoke` it owns its transaction, because the records must follow the commit; `dry_run` (the default) rolls back and stays silent
src/core/utils.py            — `format_utc_iso(dt)` ISO 8601 with Z suffix
src/core/monitors.py         — The dead-man's timer (#56): `deadline_for` (anchored on `created_at` until the first check-in, so a probe that was never wired up still alerts), `is_overdue`, `should_alert` (fires on the crossing into `missing`; `renotify_seconds` opts into repeats), the built-in `missing_notification`/`recovery_notification` wording — built in because a consumer that has stopped reporting cannot supply a template for the fact that it stopped — and `sweep_monitors()`, which marks a monitor missing whether or not the alert reached anyone
src/core/crypto.py           — Fernet encryption for Apprise URLs at rest; requires `NOTIFIER_SECRET_KEY` env var; `encrypt_apprise_url` / `decrypt_apprise_url`
src/core/notifications/      — Apprise dispatch path + plugin catalog + Jinja rendering
src/core/notifications/dispatcher.py    — `dispatch_to_channel(*, apprise_url_encrypted, title, body, notify_type)`; per-channel format negotiation (HTML-native plugins like `mailto://` get a Markdown→HTML rewrite via `markdown_to_email_html`; others receive raw Markdown unchanged); ContextVar-isolated Apprise WARNING capture; AppriseAsset branding via `_ASSET`
src/core/notifications/apprise_builder.py — Plugin catalog introspection + URL assembly: `list_plugins()`, `get_plugin_detail(schema)`, `assemble_url(schema, tokens, variant_index)`; `_build_catalog()` and `_list_plugins_cached()` are `lru_cache`d
src/core/notifications/delivery.py      — `deliver(...)`: insert a Dispatch, fan out to each channel, record a DispatchAttempt each, aggregate the status. Extracted from the dispatch route when monitors arrived (#56) — the dispatch endpoint, a check-in carrying findings, and the sweep all need it, and the sweep has no HTTP request behind it, so this raises nothing HTTP-shaped and commits nothing
src/core/notifications/render.py        — Jinja2 strict rendering: `render_template(s, variables)` (StrictUndefined; raises on syntax + undefined refs)
src/core/notifications/validate.py      — JSON Schema variables validation against template schema; raises a typed VariablesValidationError with field path, or its `SchemaDocumentError` subclass when the *schema* is at fault (routes report that as `variables_schema`). `check_schema_document` guards the schema and runs in two places: `src/api/schemas/types.py` (JSONSchemaDict) rejects a malformed one on template write, and `validate_variables` re-checks at dispatch for rows stored before that landed. Two escape hatches are closed there, both 500s otherwise: `check_schema` accepts an unknown `type` only until validation time, and it accepts a `$ref` it can never resolve — external refs are refused on write, dangling local pointers resolved, and `referencing.Unresolvable` caught at dispatch (#28)
src/core/notifications/html_render.py   — Markdown→HTML pipeline (mistune) for HTML-native channels; `markdown_to_email_html(body)` runs source through a custom `_DiffAwareRenderer` that styles ```diff fenced blocks with the GitHub palette via inline CSS; pure functions, no I/O
src/core/notifications/constants.py     — `APP_URL_ENV_VAR` (`NOTIFIER_APP_URL`, read by `dispatcher._build_asset()`; unset ships no branding link at all); `DispatchStatus` + `DispatchAttemptStatus` StrEnums (canonical server-side status values used in dispatch route and cross-checked against Pydantic schema Literals)
tests/                       — Mirrors src/ structure; integration tests use real Postgres via TEST_DATABASE_URL. `tests/conftest.py` pins `DATABASE_URL` to `TEST_DATABASE_URL` at module level so a shell that sourced production secrets cannot leak them into a test run
tests/ci/                    — Drift tests for the build surface: the pinned interpreter and locked install CI depends on, the ruff selector list that is the whole static-analysis surface, and the dependency policy every specifier is held to. Assertion-by-assertion inventory in the drift-test annex
tests/deploy/                — Drift tests for the deploy surface: the systemd units, the sweep pair, the launch and env-loading scripts, the SocratiCode config and the skills-refresh and SocratiCode-health hooks. Assertion-by-assertion inventory in the drift-test annex
clients/python/              — `notifier-client` Python SDK; separate `pyproject.toml` + venv (`uv sync` from this dir); `src/notifier_client/generated/` is regenerated from `/openapi.json` via `clients/python/scripts/regen.sh` and must never be hand-edited; `sdk-staleness.yml` fails any push to main or PR that leaves it stale, and also runs the SDK unit suite against the regenerated client. Public types in `notifier_client.types`; sub-clients under `client.channels`, `client.templates`, `client.apprise`, `client.monitors` (`checkin()` is the one auto-retried write — a dropped heartbeat looks like a dead consumer, and the replay just overwrites the previous check-in).
.github/                     — Workflows: `ci.yml` (`lint`, `test`, `migrations` on push to main, PRs, and manual dispatch; the `migrations` job is the only gate covering a broken migration chain, which the suite structurally cannot reach because conftest builds schema with `create_all`) and `sdk-staleness.yml` (regenerates the SDK, fails on drift, runs the SDK unit suite). Both take `permissions: contents: read` and cancel in-progress runs for PRs only — never for main, which is the deployed code. Plus `dependabot.yml` (#33): weekly uv bumps over both dependency tables (`versioning-strategy: increase-if-necessary`, dev-group churn grouped per directory, runtime deps as individual PRs) and a `github-actions` block for the workflows' own pins
deploy/                      — Systemd units, both binding this host's tailnet address alone (#43): `notifier.service` (production, :9000, carries `NOTIFIER_ALLOW_PROD_DB=1`, ExecStart is `scripts/serve.sh` because systemd reads `EnvironmentFile=` before `ExecStartPre` and so cannot hand the resolved address to ExecStart) and `notifier-dev.service` (dev endpoint, :9001, `notifier_dev`, runs `scripts/dev_server.sh` with the reloader off and no production opt-in, writes its own `build-id-dev` so `/health` names a commit, and bounds restarts wide enough to ride out a slow Postgres at boot — the base URL consumers point non-production processes at, #24). Plus the sweep pair (#56): `notifier-sweep.timer` + `notifier-sweep.service` (production, every 60s, carries `NOTIFIER_ALLOW_PROD_DB=1`) and `notifier-sweep-dev.{timer,service}` (dev database via `NOTIFIER_SWEEP_DEV=1`, no opt-in). A timer rather than a task inside the API process: an alerter that rides the thing it watches stops reporting exactly when it is needed. Plus the memory reservation this 3.8 GiB no-swap host needs (#74): `MemoryLow=`/`OOMScoreAdjust=-500` on the production pair and deliberately neither on the dev pair, `99-notifier-memory.conf` for the atomic-allocation reserve no cgroup setting can supply, and `earlyoom.default`, whose regexes stay space-free because systemd word-splits the unquoted `$EARLYOOM_ARGS`
docs/                        — Reference docs (COMMANDS, DEPLOYMENT, SKILLS, SOCRATICODE, `reference/tailscale.md`, `reference/monitors.md`); `docs/plans/` holds implementation plans
scripts/                     — Helper scripts: the launch paths, env loading, credential and tenant tooling, and the sweep; per-script inventory in reference/scripts.md
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


## Lint policy

`[tool.ruff.lint] select` is the entire static-analysis surface between a
commit and CI: `pre-commit` runs ruff and never pytest, and CI's `lint` job
runs the same two ruff commands. A family dropped from that list stops
checking without failing anything, so `tests/ci/test_lint_selectors.py`
asserts the list by name.

**`ASYNC` (#66).** Every route handler in `src/api/routes/` is `async def`,
sharing one event loop with the Apprise dispatch path. A blocking call in a
handler — sync `httpx`, `requests`, `time.sleep`, `open()`, a subprocess —
stalls every concurrent request, and the symptom is latency under load rather
than a failure anyone can attribute to a line. The family reported **0
findings** on adoption; its whole value is prospective, which is also why a
clean `ruff check .` is not evidence it is still selected.

Its limit is worth knowing before trusting it: **`ASYNC210` matches blocking
HTTP by call name** (`httpx.get`, `requests.post`) and does not infer the type
of an arbitrary client instance. `client.get(...)` inside an `async def`
passes, which is exactly the shape in `scripts/rotate_key.py` and why the
count was 0 rather than 1. The rule narrows the hole; it does not close it,
and a clean run is not proof no handler blocks.

**`FAST`.** 62 findings on adoption, none a bug — a style decision, landed
separately from the one-line `ASYNC` change and in two commits, because both
fixes are marked unsafe for real reasons:

- **`FAST001`** (20) drops `response_model=` where the return annotation says
  the same thing. Where the two *disagree*, `response_model=` is what
  serializes — so the check before adopting was the OpenAPI dump, which is
  byte-identical across the change, leaving
  `clients/python/.../generated/` unchanged and `sdk-staleness.yml` with
  nothing to trip on. `health.py`'s `ready()` is the site where they do
  disagree (it returns `JSONResponse`), and it correctly kept its
  `response_model=`.
- **`FAST002`** (42) replaces `x: X = Depends(...)` with
  `Annotated[X, Depends(...)]` across every route handler — its own commit
  because it touches the default-argument shape of every endpoint at once.
  Its reach stops at path operations, the family's blind spot alongside
  `ASYNC210`'s: the dependency *functions* in `src/api/deps.py` are not
  endpoints, so `require_api_key` keeps `= Depends(api_key_header)` with ruff
  clean. That shape is correct there, not an unconverted leftover.


## Dependency policy

**Dependencies:** (both `pyproject.toml` files — the service's and the SDK's)
- Every specifier carries an upper bound, runtime and dev group alike
- A `0.x` dependency caps at the next *minor* above the locked version (`<0.38`, never `<1`) — pre-1.0 projects ship breaking changes in minors
- Every runtime dependency has an importer under `src/`, or an `IMPORT_LESS` entry in `tests/ci/test_dependencies.py` stating how it is reached instead
- Every third-party module `src/` imports is declared — a package that arrives transitively takes its floor from whoever pulls it in (#32)
- All of these are asserted there, so a dependency added without them fails the suite
- The caps make new minors invisible to `uv lock`, so `.github/dependabot.yml` proposes each bump as a CI-gated PR (#33) — `tests/ci/test_dependabot.py` guards that config, since a broken one stops producing PRs silently
