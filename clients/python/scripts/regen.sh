#!/usr/bin/env bash
# Regenerate clients/python/src/notifier_client/generated/ from notifier's
# OpenAPI schema. Idempotent — safe to run repeatedly.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SDK_DIR="${REPO_ROOT}/clients/python"
GEN_DIR="${SDK_DIR}/src/notifier_client/generated"

cd "${REPO_ROOT}"
TMP_SPEC="$(mktemp -t notifier-openapi-XXXXXX.json)"
trap 'rm -f "${TMP_SPEC}"' EXIT
uv run python scripts/dump_openapi.py > "${TMP_SPEC}"

cd "${SDK_DIR}"
rm -rf "${GEN_DIR}"
uv run openapi-python-client generate \
    --path "${TMP_SPEC}" \
    --meta none \
    --output-path "${GEN_DIR}" \
    --overwrite

# No ruff pass of our own here: `generated/` is excluded from every ruff run
# (`extend-exclude` in clients/python/pyproject.toml). The output is still
# coupled to the ruff version, though — with `--meta none` and no config file,
# openapi-python-client runs its own post-hooks, `ruff check . --fix-only
# --extend-select=I` then `ruff format .`, with the SDK venv's ruff. A ruff bump
# that changes formatting therefore surfaces in CI as "SDK generated/ is stale"
# on the bump PR itself; regenerate and commit with it (ruff 0.17, #125).
echo "Regenerated: ${GEN_DIR}"
