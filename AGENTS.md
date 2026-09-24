# notifier — Agent Guidelines

Be terse. Prefer fragments over full sentences. Skip filler and preamble. Sacrifice grammar for density. Lead with the answer or action.

## Project Overview

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates + JSON-Schema variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; the service renders, validates, dispatches, and logs every attempt.

It also runs **dead-man's timers** (#56): a consumer checks in on a cadence, and the *absence* of a check-in is itself an alert — [docs/reference/monitors.md](docs/reference/monitors.md).

**Scope: publication only.** Notifier publishes what consumers send; it does not originate alerts. Monitors are the one exception, **frozen** until they are extracted into a separate service (#83): existing monitors keep running and get fixes, and none are added.

First consumer is the `watcher` project (Cannabis Observer); the API stays consumer-agnostic, with no domain concepts leaking into the service.

## Development Methodology

TDD required. Red → Green → Refactor. No production code without a failing test first.

## Environment & Tooling

Python ≥3.12, uv, pytest, ruff.

## Continuous Integration

`.github/workflows/ci.yml` runs `lint`, `test`, and `migrations` on every push
to main, on PRs, and on manual dispatch. `sdk-staleness.yml` runs on the same
triggers when `src/api/**`, `scripts/dump_openapi.py`, or `clients/python/**`
changes.

Never re-derive these from the YAML:

- **`pre-commit` runs ruff only, never pytest.** A clean commit hook says
  nothing about correctness — only CI does.
- **CI pins CPython 3.12 and installs with `uv sync --locked`, deliberately.**
  `[tool.coverage.run] core = "sysmon"` needs ≥3.12 and coverage ≥7.10; below
  either it falls back silently and reports ~6 points low against the live
  `fail_under = 80`. `tests/ci/` asserts both, so a runner change fails loudly.

<!-- BEGIN socraticode-policy -->
## Code Exploration Policy

SocratiCode is the preferred semantic-search tool here once indexed. The store
is **shared, on `co-index`** (#57), and holds everything persisted — chunks,
graph and context artifacts alike. Manifest:
`.socraticodecontextartifacts.json`.
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
| Imports/dependents of a file · blast radius of a change | `codebase_graph_query` / `codebase_impact` (takes `target`) |
| The same question **across cohort repos** | `codebase_search` with `includeLinked: true` |

`includeLinked` defaults to **false** and reaches `codebase_search` alone;
every other tool is single-project however many repos the store holds.

Full tool table, prefetch query, per-tool guidance: [`docs/SOCRATICODE.md`](docs/SOCRATICODE.md).
<!-- END socraticode-policy -->

## Project Layout

Two packages, one boundary: `src/api/` is transport (routes, Pydantic schemas, auth deps) and `src/core/` is domain logic (models, crypto, Apprise dispatch, Jinja rendering). Core never imports api.

`/api/v1/` is versioned and auth-guarded; `/health` and `/ready` are root-level, unauthenticated, and name the database they serve — assert on `environment`, never `build` (#58). `clients/python/src/notifier_client/generated/` is generated from `/openapi.json` — never hand-edit it; `sdk-staleness.yml` fails a stale push to main or PR.

Per-module inventory: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Infrastructure

**Own VM since #43.** `notifier.exe.xyz` (exe.dev, `pdx`) runs this service and
its PostgreSQL 16 cluster, nothing else — dev and production both. Code
committed to main is the deployed code.

| Service | Framework | Port | Managed by |
|---|---|---|---|
| API (live) | FastAPI | 9000 | `systemctl` (`notifier.service`), production DB |
| API (dev) | FastAPI | 9001 | `systemctl` (`notifier-dev.service`), `notifier_dev` |
| Sweep (live) | systemd timer, 60s | — | `notifier-sweep.timer` → `.service`, production DB |
| Sweep (dev) | systemd timer, 60s | — | `notifier-sweep-dev.timer` → `.service`, `notifier_dev` |

**3.8 GiB, no swap**, shared with your session: past the ceiling nothing is
OOM-killed, the kernel fails atomic allocations and the service drops. Hence
**never cap the service** and **never install at launch** — SocratiCode is
pinned under `~/.socraticode/pin` (#74,
[reservation](docs/reference/memory-reservation.md)).

The two sweeps are the only thing watching for consumer silence, so a timer
that stops is a silent outage of the outage detector: `systemctl list-timers
'notifier-sweep*'` is the check. Why a timer and not a task in the API
process: [docs/reference/monitors.md](docs/reference/monitors.md).

Both always-on. **9001 is the development endpoint consumers point at** — it
accepts `development`-marked API keys, which 9000 refuses (#24).

**Both bind this host's tailnet address alone, never `0.0.0.0`** — so the API
is unreachable from exe.dev's internal `10.42.0.0/16`, from the proxy and from
the internet, and the Tailscale ACL decides who gets in. `scripts/tailnet_bind.sh`
fails loudly rather than falling back to a wider bind. That, and the boot race
it buys: [docs/reference/tailscale.md](docs/reference/tailscale.md).

Other tailnet nodes reach `http://notifier:9000` / `:9001`. **On this VM both
`127.0.0.1:9000` and `http://notifier:9000` fail** — `/etc/hosts` maps
`notifier` to `127.0.1.1`, which nothing binds. Use
`curl "http://$(tailscale ip -4):9000/health"`.

## Server Lifecycle

**Port 9000 belongs to systemd.** Never start uvicorn manually on port 9000.

| Situation | Action |
|---|---|
| Code committed to main | `sudo systemctl restart notifier notifier-dev` |
| Testing a worktree/branch | `sudo systemctl stop notifier-dev`, then `./scripts/dev_server.sh` |
| Debugging live / dev | `sudo journalctl -u notifier -f` · `-u notifier-dev -f` |
| After editing a unit in `deploy/` | `sudo systemctl daemon-reload`, then restart both |
| After DB model changes | `uv run alembic upgrade head`, the same against `DEV_DATABASE_URL`, then restart both |
| Checking the dead-man's sweep | `systemctl list-timers 'notifier-sweep*'`, `sudo journalctl -u notifier-sweep -f` |
| Which key was minted, revoked, or destroyed with its tenant | `journalctl -t notifier-keys` |
| Forcing a sweep now | `sudo systemctl start notifier-sweep.service` |

Fuller spellings, with the reasoning beside each: [docs/DEPLOYMENT.md § Routine ops](docs/DEPLOYMENT.md#routine-ops).

**Dev server by hand** ([what the script checks, and the unit's reloader](docs/COMMANDS.md#development)):

```bash
sudo systemctl stop notifier-dev   # the unit owns 9001; take it first
./scripts/dev_server.sh            # foreground, --reload on
sudo systemctl start notifier-dev  # hand it back
```

**Never hand-run uvicorn.** Sourcing `/etc/notifier/.env` points
`DATABASE_URL` at **production**, which is how a "dev" server once shared the
live database (#22) — still the risk here, where both endpoints share a host
and a cluster and only the database differs. `src/core/db_safety.py` refuses
any database not ending `_test` or `_dev`, and its opt-in
`NOTIFIER_ALLOW_PROD_DB=1` lives in the unit, never in an env file.

**After finishing work:** always restart both — they serve one working tree, so restarting only the live one leaves dev answering from stale code:

```bash
sudo systemctl restart notifier notifier-dev
```

## Environment Variables

Two env files, loaded in order (later values override):

1. **`/etc/notifier/.env`** — production secrets (`DATABASE_URL`, `NOTIFIER_SECRET_KEY`); managed by hand on the VM, and survives repo resets and worktree switches.
2. **`.env`** (repo root, git-ignored) — dev/agent secrets (`GH_TOKEN`, `TEST_DATABASE_URL`, `DEV_DATABASE_URL`). Never commit.

The systemd service loads both automatically. Source them for shell commands
— never word-split through `xargs`, which corrupts any value containing spaces
or quotes:

```bash
. scripts/load_env.sh
```

**This leaves `DATABASE_URL` pointing at production.** That is correct for
`alembic upgrade head` and for `systemctl`, and wrong for everything else. Use
`./scripts/dev_server.sh` for a server; `pytest` pins `DATABASE_URL` to the
test database itself.

Every variable, what sets it and why: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#environment-variables).

## Common Commands

```bash
uv sync

# Load environment first — pytest needs TEST_DATABASE_URL, alembic needs
# DATABASE_URL. Leaves DATABASE_URL on production; see below.
. scripts/load_env.sh

uv run pytest

# Run a subset of tests (skip the coverage gate, which measures all of src/)
uv run pytest --no-cov tests/core/test_utils.py

# Run integration tests (requires PostgreSQL)
uv run pytest -m integration

uv run ruff check .

# Format (both gates below run at ship/review time — `--check` is the gate)
uv run ruff format .
uv run ruff format --check .

# Run every gate the way pre-commit does
uv run pre-commit run --all-files
uv run pre-commit install            # once per clone — installs it as a git hook

uv run alembic upgrade head          # apply all migrations
uv run alembic revision --autogenerate -m "description"  # generate new migration
```

Full reference: [docs/COMMANDS.md](docs/COMMANDS.md).

## Agent Skills

Skills live in `skills/` (agentskills.io) and `.claude/skills/` (Claude Code); local overrides in `skills/` shadow the vendored copy. Inventory, sources and override notes: [docs/SKILLS.md § Skills Inventory](docs/SKILLS.md#skills-inventory).

## Conventions

**Commit Messages:**
```
#<number> [type]: <description>      # with issue
[type]: <description>                # without issue
```
Types: feat, fix, refactor, docs, test, chore, release (version bumps only — see [docs/RELEASING.md](docs/RELEASING.md))

**Logging:** `logger = get_logger(__name__)`, imported from `src.core.logging`.
Entry points only: call `configure_logging()` once — it binds **stdout**.
Credential scripts call `configure_script_logging()` instead ([the audit
channel](docs/DEPLOYMENT.md#the-credential-audit-channel-67)).

**Date & Time:**
- All UTC
- ISO 8601: `YYYY-MM-DDTHH:MM:SS.ffffffZ` (timestamps), `YYYY-MM-DD` (dates)

**Lint:** ruff `select` is the whole gate between a commit and CI (`pre-commit` skips pytest), and `tests/ci/test_lint_selectors.py` asserts the list, since `ASYNC` finds nothing here and a clean run proves nothing. **`ASYNC210` matches blocking HTTP by *name*** — `client.get(...)` on an instance passes, so green lint is not proof no handler blocks. [Detail](docs/ARCHITECTURE.md#lint-policy).

**Dependencies:** four rules, all asserted by `tests/ci/test_dependencies.py` — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#dependency-policy) before adding or bumping one

**General:**
- No inline module imports; all at file top, explicit only
- Docstrings for public modules, classes, functions
- Test structure mirrors source (`src/foo.py` → `tests/test_foo.py`)
- Small, focused functions

## API Boundary Principles

The service is consumer-agnostic. Resist these temptations:

- **Do not** introduce a top-level `event_type` field on dispatch — that's consumer taxonomy. Consumers put it in `metadata` if they want it indexed.
- **Do not** infer routing/subscriptions in v0 — consumers pass `channel_ids` explicitly. Subscription model is v1.
- **Do not** add a monitor or monitor consumer (#83 freeze). A consumer that wants to raise alerts uses `/dispatch`; silence detection waits for the extracted service.
- **Do not** fetch consumer data — no diff loading, no snapshot reads. Consumers ship rendered values via `variables`.
- **Do not** branch on tenant identity inside business logic. Tenancy is enforced at the auth layer; the rest of the code treats `tenant_id` as a partition key.
- **Do** validate `variables` against the template's `variables_schema` on dispatch; a miss is a 422 naming the field path. The *schema itself* is checked twice — on template write, where a malformed one is a 422 naming `body.variables_schema`, and again at dispatch, which catches rows stored before that guard (#28).
- **Do** render with `StrictUndefined` so unbound references fail loudly rather than silently producing empty output.
- **Do** require `idempotency_key` to be tenant-scoped and unique-where-not-null; replay must be safe.
- **Do** treat a monitor check-in's `variables` as opaque and its `status` as the consumer's own judgement: whether a report warrants notifying is consumer taxonomy, and a broker maps its own `finding_count > 0` onto `alert`. Whether one *arrived* is the part notifier cannot infer (#56).
- **Do** mark every API key with an `environment` (`production` | `development`); a production deployment refuses `development` keys with 403. It is the only layer that sees a consumer's dev process calling production over HTTP — a database guard cannot (issue #22).

## Detail Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — per-module inventory including `tests/` and `deploy/`, and the dependency policy every specifier is held to
- [docs/COMMANDS.md](docs/COMMANDS.md) — every runnable command with its flags
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — VM setup, unit install, routine ops, and the environment-variable reference
- [docs/RELEASING.md](docs/RELEASING.md) — cutting a release: the one version, every site mirroring it, the CI gates, and how a consumer adopts the SDK
- [docs/reference/monitors.md](docs/reference/monitors.md) — the dead-man's timer: why absence is the alert, the check-in contract, and what nothing watches
- [docs/reference/tailscale.md](docs/reference/tailscale.md) — the tailnet: node identity, ACL, the bind decision and the boot race it buys
- [docs/SOCRATICODE.md](docs/SOCRATICODE.md) — tool table, graph-health guidance, the shared store's traps ([shared-store.md](docs/reference/shared-store.md)), and this repo's measured yield
- [docs/SKILLS.md](docs/SKILLS.md) — skill layout, vendored submodules and refresh procedure, full inventory
