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
    --overwrite \
    --fail-on-warning

# No ruff pass of our own here: `generated/` is excluded from every ruff run
# (`extend-exclude` in clients/python/pyproject.toml). The output is still
# coupled to ruff, though — with `--meta none` and no config file,
# openapi-python-client runs its own post-hooks, `ruff check . --fix-only
# --extend-select=I` then `ruff format .`, with the SDK venv's ruff and the
# `[tool.ruff]` settings in clients/python/pyproject.toml. A ruff bump that
# changes formatting, or an edit to those settings, therefore surfaces in CI as
# "SDK generated/ is stale" on that PR itself; regenerate and commit with it
# (ruff 0.17, #125). The SDK's ruff floor tracks the version the committed
# output was formatted with.
#
# `--fail-on-warning`: a ruff missing from PATH is only a warning to the
# generator, which then skips both hooks and exits 0 with unformatted output —
# a "stale" failure that names the wrong cause.
echo "Regenerated: ${GEN_DIR}"
