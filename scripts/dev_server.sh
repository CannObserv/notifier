#!/usr/bin/env bash
# Guarded dev-server launch. Use this instead of hand-running uvicorn.
#
# The old recipe sourced /etc/notifier/.env — which sets DATABASE_URL to
# production — and then ran uvicorn on 9001, so the "dev" server shared one
# database with the live service on 9000 (issue #22, root incident
# CannObserv/archiver#98).
#
# This script loads secrets the same way, then overrides DATABASE_URL with
# DEV_DATABASE_URL and hands the result to src.core.db_safety for the
# production check. The parsing lives in python only — bash never
# reimplements it, so the two cannot diverge.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "${NOTIFIER_DEV_SERVER_SKIP_ENV_FILES:-}" != "1" ]]; then
  # shellcheck disable=SC1091
  . scripts/load_env.sh
fi

# Never inherit the production opt-in; it belongs to the systemd unit alone.
unset NOTIFIER_ALLOW_PROD_DB

if [[ -z "${DEV_DATABASE_URL:-}" ]]; then
  cat >&2 <<'MSG'
dev_server: DEV_DATABASE_URL is not set.

The dev server must not share the production database. Create a dev database
and point DEV_DATABASE_URL at it in the repo .env (git-ignored):

  createdb notifier_dev
  echo 'DEV_DATABASE_URL=postgresql+asyncpg://USER@localhost/notifier_dev' >> .env
  DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head

The name must end in _test or _dev; see src/core/db_safety.py.
MSG
  exit 1
fi

export DATABASE_URL="$DEV_DATABASE_URL"

uv run python -m src.core.db_safety

# An unmigrated dev database starts cleanly and then 500s on every
# authenticated request with "relation ... does not exist" (issue #23), so
# check migration state here where the message can say what to do about it.
# `alembic current` prints the revision on stdout: non-zero means the database
# is unreachable, empty stdout means reachable but never migrated.
if ! revision="$(uv run alembic current 2>/dev/null)"; then
  echo "dev_server: cannot read migration state — is the dev database reachable?" >&2
  exit 1
fi
if [[ -z "${revision//[[:space:]]/}" ]]; then
  cat >&2 <<'MSG'
dev_server: the dev database has no migrations applied.

  DATABASE_URL="$DEV_DATABASE_URL" uv run alembic upgrade head
MSG
  exit 1
fi

exec uv run uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port 9001 \
  --reload \
  --log-config src/core/log_config.json
