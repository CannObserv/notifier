# notifier

[![CI](https://github.com/CannObserv/notifier/actions/workflows/ci.yml/badge.svg)](https://github.com/CannObserv/notifier/actions/workflows/ci.yml)

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates and JSON-Schema-validated variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; notifier renders, validates, and dispatches.

## Quick start

```bash
uv sync
uv run pre-commit install   # once per clone — gates commits on ruff check + format
                            # note: no tests. Only CI runs the suite.

# Load secrets, then apply migrations. This leaves DATABASE_URL pointing at
# production, which is what alembic wants here — main is the deployed code.
. scripts/load_env.sh
uv run alembic upgrade head

# Dev server: guarded, port 9001, runs against DEV_DATABASE_URL (notifier_dev)
./scripts/dev_server.sh
```

Live service runs on port 9000 via systemd; dev server uses 9001. Both bind
this host's tailnet address only — reachable as `http://notifier:9000` from the
`cannobserv.org.github` tailnet, not from loopback or the internet. Never
hand-run uvicorn — `scripts/dev_server.sh` exists because the old recipe
pointed the dev server at the production database (issue #22).

See `AGENTS.md` for conventions, `docs/ARCHITECTURE.md` for the per-module layout, and `docs/COMMANDS.md` for the full command reference.
