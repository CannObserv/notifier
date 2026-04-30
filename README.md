# notifier

Multi-tenant notifications service. Apprise-backed dispatcher with Jinja2 templates and JSON-Schema-validated variable bags. Consumers send `{template_id | inline templates, variables, channel_ids}`; notifier renders, validates, and dispatches.

## Quick start

```bash
uv sync
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run alembic upgrade head
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 9001 --reload
```

Live service runs on port 9000 via systemd; dev server uses 9001.

See `AGENTS.md` for conventions and `docs/COMMANDS.md` for the full command reference.
