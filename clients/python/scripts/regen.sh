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

# No ruff format pass here on purpose. openapi-python-client's output is
# already format-clean, and `generated/` is excluded from every ruff run
# (`extend-exclude` in clients/python/pyproject.toml), so formatting it here
# would couple the committed tree to the ruff version: a formatter bump would
# rewrite these files and surface in CI as a misleading "SDK generated/ is
# stale" failure. Keep this script a pure function of the OpenAPI spec.
echo "Regenerated: ${GEN_DIR}"
