# Python SDK (notifier-client) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a typed async Python SDK from notifier's OpenAPI schema, shipped as a separate `notifier-client` package under `clients/python/`, consumable by watcher and future projects.

**Architecture:** `openapi-python-client` regenerates a `generated/` subpackage from `app.openapi()` (dumped via a tiny script — no live server needed in CI). A hand-written `NotifierClient` facade composes (does not subclass) the generated client. Cross-cutting concerns — `X-API-Key` injection, retries with exponential backoff, 429 `Retry-After` honoring, idempotency-key passthrough with `AUTO` ULID sentinel, redacting log filter, typed error hierarchy — live in the wrapper layer. CI fails any PR touching `src/api/**` whose generated client is stale.

**Tech Stack:** Python ≥3.12, `httpx` (async), `openapi-python-client` (codegen), `respx` (mocking), `pytest-asyncio`, `python-ulid`.

**Issue:** [CannObserv/notifier#1](https://github.com/CannObserv/notifier/issues/1) — closes [CannObserv/watcher#132](https://github.com/CannObserv/watcher/issues/132) once watcher consumes it.

---

## File Structure

```
clients/python/
  pyproject.toml                          ← name="notifier-client", build-system=hatchling
  README.md                               ← install + usage + version-pinning policy
  src/
    notifier_client/
      __init__.py                         ← re-exports NotifierClient, errors, RetryConfig
      client.py                           ← NotifierClient facade (auth, retry hookup, idempotency)
      errors.py                           ← NotifierError → AuthError, ValidationError, RateLimited, ServerError
      retry.py                            ← RetryConfig dataclass + RetryTransport (httpx transport)
      retry_after.py                      ← parse_retry_after(): seconds | HTTP-date
      logging.py                          ← redacting Filter masking X-API-Key
      idempotency.py                      ← AUTO sentinel + resolve_idempotency_key()
      generated/                          ← openapi-python-client output; never hand-edited
        ...                               ← (created by regen script)
  tests/
    conftest.py                           ← respx + asyncio fixtures
    test_retry_after.py                   ← parse seconds, parse HTTP-date, parse junk → None
    test_retry_config.py                  ← defaults, customization, retry_on set
    test_retry_transport.py               ← respx: retry on 5xx, no retry on 4xx, 429 honors Retry-After, exhausted → RateLimited
    test_errors.py                        ← parsing 422 field-path body → ValidationError.field_path
    test_idempotency.py                   ← AUTO → ULID; explicit → passthrough; None → header omitted
    test_logging.py                       ← redacting filter masks X-API-Key in records
    test_client.py                        ← respx round-trip: dispatch happy path, dispatch with idempotency, dispatch never auto-retried without key
    test_smoke_integration.py             ← @pytest.mark.integration; against localhost:9001
  scripts/
    regen.sh                              ← dump openapi → run codegen → format
scripts/
  dump_openapi.py                         ← (root scripts/) imports notifier app, prints app.openapi() JSON
.github/
  workflows/
    sdk-staleness.yml                     ← on PRs touching src/api/**, regen + git diff --exit-code
```

**Boundaries:**
- `generated/` is opaque output. The wrapper imports its types and request functions but never subclasses generated classes (codegen renames internals between versions).
- `client.py` is the only public surface. Everything else is implementation detail re-exported through `__init__.py`.
- `retry.py` knows nothing about notifier — just httpx + RetryConfig. Could be lifted to a separate package later.

---

## PR 1 — Scaffold the package

**Files:**
- Create: [clients/python/pyproject.toml](clients/python/pyproject.toml)
- Create: [clients/python/README.md](clients/python/README.md)
- Create: [clients/python/src/notifier_client/__init__.py](clients/python/src/notifier_client/__init__.py)
- Create: [clients/python/tests/__init__.py](clients/python/tests/__init__.py)
- Create: [clients/python/tests/test_smoke.py](clients/python/tests/test_smoke.py)

### Task 1.1: Write the import smoke test

- [ ] **Step 1: Create the test**

`clients/python/tests/test_smoke.py`:
```python
def test_package_imports():
    import notifier_client  # noqa: F401
```

- [ ] **Step 2: Verify it fails**

Run: `cd clients/python && uv run --isolated pytest tests/test_smoke.py -v`
Expected: FAIL — `notifier-client` not installable yet.

### Task 1.2: Create the pyproject.toml

- [ ] **Step 1: Write pyproject.toml**

`clients/python/pyproject.toml`:
```toml
[project]
name = "notifier-client"
version = "0.1.0"
description = "Async Python SDK for the notifier service. Generated from notifier's OpenAPI schema; pinned 1:1 with server version."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28.0,<1",
    "python-ulid>=3.0.0,<4",
    "attrs>=24",                   # required by openapi-python-client output
    "python-dateutil>=2.9",        # required by openapi-python-client output
]

[dependency-groups]
dev = [
    "pytest>=8.0,<9",
    "pytest-asyncio>=1.3.0,<2",
    "respx>=0.22",
    "openapi-python-client>=0.21,<1",
    "ruff>=0.9,<1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short -m 'not integration'"
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
markers = [
    "integration: marks tests that hit a live notifier; excluded by default (run with -m integration)",
]
filterwarnings = ["error::DeprecationWarning"]

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["src/notifier_client/generated/"]   # generated code — don't lint

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP"]

[tool.ruff.lint.isort]
known-first-party = ["notifier_client"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/notifier_client"]
```

- [ ] **Step 2: Write the package __init__**

`clients/python/src/notifier_client/__init__.py`:
```python
"""notifier-client — async Python SDK for the notifier service.

Pinned 1:1 with notifier server version. See README for usage.
"""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write the README skeleton**

`clients/python/README.md`:
````markdown
# notifier-client

Async Python SDK for the [notifier](https://github.com/CannObserv/notifier) service.

## Install

```bash
uv add "notifier-client @ git+ssh://git@github.com/CannObserv/notifier.git@v0.1.0#subdirectory=clients/python"
```

Versions are pinned 1:1 with the notifier server. SDK `0.x.y` ⇔ notifier `0.x.y`.

## Usage

```python
from notifier_client import NotifierClient

async with NotifierClient(base_url="https://notifier.exe.xyz", api_key="nk_...") as client:
    result = await client.dispatch(
        template_id="...",
        variables={"strain": "Blue Dream"},
        channel_ids=["..."],
        idempotency_key="watcher-event-1234",
    )
```

## Development

This package is co-located with the notifier server in [CannObserv/notifier](https://github.com/CannObserv/notifier). The `generated/` subdirectory is regenerated from `app.openapi()` — never edit by hand. See [PR #1](https://github.com/CannObserv/notifier/issues/1).
````

- [ ] **Step 4: Run smoke test, expect pass**

Run: `cd clients/python && uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS — package installs and imports.

- [ ] **Step 5: Commit**

```bash
git add clients/python/
git commit -m "#1 feat: scaffold notifier-client package"
```

---

## PR 2 — OpenAPI dump + regen + CI staleness check

**Files:**
- Create: [scripts/dump_openapi.py](scripts/dump_openapi.py)
- Create: [clients/python/scripts/regen.sh](clients/python/scripts/regen.sh)
- Create: [.github/workflows/sdk-staleness.yml](.github/workflows/sdk-staleness.yml)
- Create: `clients/python/src/notifier_client/generated/` (committed regen output)
- Modify: [docs/COMMANDS.md](docs/COMMANDS.md) (add regen command)

### Task 2.1: Write the OpenAPI dump script

- [ ] **Step 1: Write a test that the dump script produces valid JSON with expected paths**

`tests/test_dump_openapi.py` (in notifier root tests):
```python
import json
import subprocess
import sys


def test_dump_openapi_emits_known_paths():
    result = subprocess.run(
        [sys.executable, "scripts/dump_openapi.py"],
        capture_output=True, text=True, check=True,
    )
    spec = json.loads(result.stdout)
    assert spec["openapi"].startswith("3.")
    paths = set(spec["paths"].keys())
    assert "/health" in paths
    assert "/ready" in paths
    assert "/api/v1/dispatch" in paths
    assert "/api/v1/templates" in paths
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/test_dump_openapi.py -v`
Expected: FAIL — script doesn't exist.

- [ ] **Step 3: Write the script**

`scripts/dump_openapi.py`:
```python
"""Dump notifier's OpenAPI schema to stdout as JSON.

Used by the SDK regen workflow and CI staleness check. Imports the FastAPI
``app`` and serializes ``app.openapi()`` — no server, no DB connection required.
"""

import json

from src.api.main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify test passes**

Run: `uv run pytest tests/test_dump_openapi.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/dump_openapi.py tests/test_dump_openapi.py
git commit -m "#1 feat: add scripts/dump_openapi.py for SDK regen"
```

### Task 2.2: Write the regen script

- [ ] **Step 1: Write the regen shell script**

`clients/python/scripts/regen.sh`:
```bash
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

uv run ruff format "${GEN_DIR}" || true   # cosmetic; don't fail regen on format diffs
echo "Regenerated: ${GEN_DIR}"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x clients/python/scripts/regen.sh
```

- [ ] **Step 3: Run regen + verify it produces output**

Run: `clients/python/scripts/regen.sh`
Expected: `clients/python/src/notifier_client/generated/` exists with `*.py` files (e.g. `client.py`, `models/`, `api/`).

Verify: `ls clients/python/src/notifier_client/generated/`

- [ ] **Step 4: Verify the SDK still installs and tests pass**

Run: `cd clients/python && uv sync && uv run pytest -v`
Expected: PASS (smoke test still imports).

- [ ] **Step 5: Commit the generated output as a baseline**

```bash
git add clients/python/scripts/regen.sh clients/python/src/notifier_client/generated/
git commit -m "#1 feat: add regen.sh and commit baseline generated client"
```

### Task 2.3: Add CI staleness workflow

- [ ] **Step 1: Write the workflow**

`.github/workflows/sdk-staleness.yml`:
```yaml
name: SDK staleness check

on:
  pull_request:
    paths:
      - "src/api/**"
      - "src/api/schemas/**"
      - "scripts/dump_openapi.py"
      - "clients/python/scripts/regen.sh"

jobs:
  staleness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install notifier deps
        run: uv sync
      - name: Install SDK dev deps
        working-directory: clients/python
        run: uv sync
      - name: Regenerate SDK
        run: clients/python/scripts/regen.sh
      - name: Fail if generated/ is stale
        run: |
          if ! git diff --exit-code clients/python/src/notifier_client/generated/; then
            echo "::error::SDK generated/ is stale. Run clients/python/scripts/regen.sh and commit the result."
            exit 1
          fi
```

- [ ] **Step 2: Update docs/COMMANDS.md**

Add a section after the existing Common Commands:
```markdown
## SDK regeneration

```bash
# Regenerate the Python SDK from notifier's OpenAPI schema
clients/python/scripts/regen.sh

# Verify SDK is not stale (mirrors CI)
git diff --exit-code clients/python/src/notifier_client/generated/
```
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/sdk-staleness.yml docs/COMMANDS.md
git commit -m "#1 feat: CI workflow fails PR if SDK generated/ is stale"
```

---

## PR 3 — Wrapper: errors, retry, idempotency, logging, NotifierClient

This is the meat. TDD — every behavior gets a failing test first.

**Files:**
- Create: [clients/python/src/notifier_client/errors.py](clients/python/src/notifier_client/errors.py)
- Create: [clients/python/src/notifier_client/retry_after.py](clients/python/src/notifier_client/retry_after.py)
- Create: [clients/python/src/notifier_client/retry.py](clients/python/src/notifier_client/retry.py)
- Create: [clients/python/src/notifier_client/idempotency.py](clients/python/src/notifier_client/idempotency.py)
- Create: [clients/python/src/notifier_client/logging.py](clients/python/src/notifier_client/logging.py)
- Create: [clients/python/src/notifier_client/client.py](clients/python/src/notifier_client/client.py)
- Modify: [clients/python/src/notifier_client/__init__.py](clients/python/src/notifier_client/__init__.py)
- Create test files matching each module.

### Task 3.1: Errors module

- [ ] **Step 1: Write tests**

`clients/python/tests/test_errors.py`:
```python
import httpx
import pytest

from notifier_client.errors import (
    AuthError,
    NotifierError,
    RateLimited,
    ServerError,
    ValidationError,
    error_from_response,
)


def _resp(status: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, json=json_body or {})


def test_auth_error_for_401():
    err = error_from_response(_resp(401, {"detail": "invalid api key"}))
    assert isinstance(err, AuthError)
    assert isinstance(err, NotifierError)
    assert err.status_code == 401


def test_auth_error_for_403():
    assert isinstance(error_from_response(_resp(403)), AuthError)


def test_validation_error_parses_field_path():
    err = error_from_response(
        _resp(422, {"detail": {"section": "variables", "path": "strain", "message": "required"}})
    )
    assert isinstance(err, ValidationError)
    assert err.field_path == "strain"
    assert err.section == "variables"
    assert "required" in str(err)


def test_validation_error_handles_pydantic_style_detail():
    # FastAPI default 422 shape: detail is a list of {loc, msg, type}
    err = error_from_response(
        _resp(422, {"detail": [{"loc": ["body", "channel_ids"], "msg": "field required", "type": "missing"}]})
    )
    assert isinstance(err, ValidationError)
    assert err.field_path == "body.channel_ids"


def test_rate_limited_carries_retry_after():
    resp = httpx.Response(status_code=429, headers={"Retry-After": "30"}, json={"detail": "slow down"})
    err = error_from_response(resp)
    assert isinstance(err, RateLimited)
    assert err.retry_after_seconds == 30


def test_server_error_for_5xx():
    assert isinstance(error_from_response(_resp(500)), ServerError)
    assert isinstance(error_from_response(_resp(503)), ServerError)


def test_generic_notifier_error_for_other_4xx():
    err = error_from_response(_resp(404, {"detail": "not found"}))
    assert isinstance(err, NotifierError)
    assert err.status_code == 404
```

- [ ] **Step 2: Verify tests fail**

Run: `cd clients/python && uv run pytest tests/test_errors.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement errors.py**

`clients/python/src/notifier_client/errors.py`:
```python
"""Typed exception hierarchy for notifier-client.

All exceptions inherit ``NotifierError``. Code that catches notifier issues
generically can catch ``NotifierError``; code that wants to react differently
to auth, validation, rate-limit, or server failures catches the specific
subclass.
"""

from __future__ import annotations

import httpx

from notifier_client.retry_after import parse_retry_after


class NotifierError(Exception):
    """Base class for all notifier-client errors."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 response: httpx.Response | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AuthError(NotifierError):
    """401 or 403 — invalid or missing API key."""


class ValidationError(NotifierError):
    """422 — request body or rendered template failed validation.

    ``section`` is one of ``"variables"``, ``"title"``, ``"body"`` (notifier's
    typed shape) or ``"body"`` for FastAPI's default validator output.
    ``field_path`` is dot-joined when notifier returns a list-style ``loc``.
    """

    def __init__(self, message: str, *, section: str | None = None,
                 field_path: str | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.section = section
        self.field_path = field_path


class RateLimited(NotifierError):
    """429 — caller exceeded rate limit. Retries are exhausted by the time this fires."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class ServerError(NotifierError):
    """5xx — server-side failure. Retried by the transport before this fires."""


def error_from_response(response: httpx.Response) -> NotifierError:
    """Map an HTTP response to the appropriate typed error."""
    status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = {}
    detail = body.get("detail") if isinstance(body, dict) else None

    if status in (401, 403):
        return AuthError(_message(detail, default="authentication failed"),
                         status_code=status, response=response)
    if status == 422:
        section, field_path, msg = _parse_validation_detail(detail)
        return ValidationError(msg, section=section, field_path=field_path,
                               status_code=status, response=response)
    if status == 429:
        return RateLimited(
            _message(detail, default="rate limited"),
            retry_after_seconds=parse_retry_after(response.headers.get("Retry-After")),
            status_code=status, response=response,
        )
    if 500 <= status < 600:
        return ServerError(_message(detail, default=f"server error {status}"),
                           status_code=status, response=response)
    return NotifierError(_message(detail, default=f"http {status}"),
                         status_code=status, response=response)


def _message(detail, *, default: str) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and "message" in detail:
        return str(detail["message"])
    return default


def _parse_validation_detail(detail) -> tuple[str | None, str | None, str]:
    """Return (section, field_path, message). Handles notifier's typed shape and FastAPI defaults."""
    if isinstance(detail, dict):
        # Notifier shape: {"section": ..., "path": ..., "message": ...}
        return (
            detail.get("section"),
            detail.get("path"),
            str(detail.get("message", "validation error")),
        )
    if isinstance(detail, list) and detail:
        # FastAPI default: [{"loc": [...], "msg": "...", "type": "..."}, ...]
        first = detail[0]
        loc = first.get("loc", []) if isinstance(first, dict) else []
        path = ".".join(str(p) for p in loc)
        return (None, path or None, str(first.get("msg", "validation error")))
    return (None, None, "validation error")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd clients/python && uv run pytest tests/test_errors.py -v`
Expected: PASS — all 7 tests green. (Will fail on `parse_retry_after` import — proceed to next task before re-running.)

- [ ] **Step 5: Commit (once retry_after.py also exists; see Task 3.2)**

### Task 3.2: Retry-After parser

- [ ] **Step 1: Write tests**

`clients/python/tests/test_retry_after.py`:
```python
from datetime import UTC, datetime, timedelta

import pytest
from email.utils import format_datetime

from notifier_client.retry_after import parse_retry_after


def test_parse_seconds_integer():
    assert parse_retry_after("30") == 30.0


def test_parse_seconds_float_rejected():
    # Spec says delta-seconds is an integer; float should be rejected (or accepted leniently?)
    # We accept float for ergonomics — tests the lenient path.
    assert parse_retry_after("1.5") == 1.5


def test_parse_http_date():
    # 60 seconds from now
    future = datetime.now(UTC) + timedelta(seconds=60)
    raw = format_datetime(future, usegmt=True)
    parsed = parse_retry_after(raw)
    assert parsed is not None
    assert 55 <= parsed <= 65    # tolerate clock skew + test timing


def test_parse_past_http_date_returns_zero():
    past = datetime.now(UTC) - timedelta(seconds=120)
    raw = format_datetime(past, usegmt=True)
    assert parse_retry_after(raw) == 0.0


def test_parse_none_returns_none():
    assert parse_retry_after(None) is None


def test_parse_garbage_returns_none():
    assert parse_retry_after("not a thing") is None


def test_parse_negative_returns_zero():
    assert parse_retry_after("-5") == 0.0
```

- [ ] **Step 2: Verify fail**

Run: `cd clients/python && uv run pytest tests/test_retry_after.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement retry_after.py**

`clients/python/src/notifier_client/retry_after.py`:
```python
"""Parse the HTTP ``Retry-After`` header (RFC 9110 §10.2.3).

Accepts either a delta-seconds value (``"30"``) or an HTTP-date
(``"Wed, 21 Oct 2026 07:28:00 GMT"``). Returns the number of seconds the
caller should wait, or ``None`` if the value is missing or unparseable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    # delta-seconds path
    try:
        seconds = float(raw)
    except ValueError:
        seconds = None
    if seconds is not None:
        return max(0.0, seconds)
    # HTTP-date path
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = (dt - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)
```

- [ ] **Step 4: Verify both test files pass**

Run: `cd clients/python && uv run pytest tests/test_errors.py tests/test_retry_after.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/python/src/notifier_client/errors.py \
        clients/python/src/notifier_client/retry_after.py \
        clients/python/tests/test_errors.py \
        clients/python/tests/test_retry_after.py
git commit -m "#1 feat: errors module + Retry-After parser"
```

### Task 3.3: RetryConfig + RetryTransport

- [ ] **Step 1: Write tests**

`clients/python/tests/test_retry_config.py`:
```python
from notifier_client.retry import RetryConfig


def test_defaults_are_reasonable():
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert cfg.backoff_base == 0.5
    assert cfg.retry_on == frozenset({500, 502, 503, 504})
    assert cfg.honor_retry_after is True


def test_customization():
    cfg = RetryConfig(max_attempts=5, backoff_base=0.1, retry_on={502})
    assert cfg.max_attempts == 5
    assert cfg.retry_on == frozenset({502})
```

`clients/python/tests/test_retry_transport.py`:
```python
import httpx
import pytest
import respx

from notifier_client.errors import RateLimited
from notifier_client.retry import RetryConfig, RetryTransport


@pytest.fixture
def fast_cfg():
    return RetryConfig(max_attempts=3, backoff_base=0.0)   # zero backoff for speed


async def _client(cfg: RetryConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://test.local",
        transport=RetryTransport(httpx.AsyncHTTPTransport(), cfg),
    )


@respx.mock
@pytest.mark.asyncio
async def test_retries_on_5xx_then_succeeds(fast_cfg):
    route = respx.get("https://test.local/health").mock(side_effect=[
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json={"ok": True}),
    ])
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_does_not_retry_on_4xx(fast_cfg):
    route = respx.get("https://test.local/health").mock(return_value=httpx.Response(404))
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 404
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_429_honors_retry_after_then_retries(fast_cfg):
    route = respx.get("https://test.local/health").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"ok": True}),
    ])
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_429_exhausted_returns_429_response(fast_cfg):
    # Transport doesn't raise — it returns the final response. The wrapper
    # converts that to RateLimited at the boundary.
    respx.get("https://test.local/health").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    async with await _client(fast_cfg) as c:
        r = await c.get("/health")
    assert r.status_code == 429


@respx.mock
@pytest.mark.asyncio
async def test_per_request_no_retry_extension_disables_retries(fast_cfg):
    route = respx.post("https://test.local/dispatch").mock(return_value=httpx.Response(503))
    async with await _client(fast_cfg) as c:
        r = await c.post("/dispatch", json={}, extensions={"notifier_no_retry": True})
    assert r.status_code == 503
    assert route.call_count == 1
```

- [ ] **Step 2: Verify fail**

Run: `cd clients/python && uv run pytest tests/test_retry_config.py tests/test_retry_transport.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement retry.py**

`clients/python/src/notifier_client/retry.py`:
```python
"""Retry transport for httpx — retries on 5xx + 429 with exponential backoff.

The transport itself never raises notifier-typed errors. It returns the final
HTTP response (success or terminal failure); the calling wrapper translates
non-2xx responses into typed errors at the boundary.

Why a transport (not an event hook): transports give us full control over the
request lifecycle, including streaming response bodies and cancellation. Hooks
are awkward for retries because they fire after the response is consumed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from notifier_client.retry_after import parse_retry_after


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    backoff_base: float = 0.5
    retry_on: frozenset[int] = field(default_factory=lambda: frozenset({500, 502, 503, 504}))
    honor_retry_after: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.retry_on, frozenset):
            object.__setattr__(self, "retry_on", frozenset(self.retry_on))


class RetryTransport(httpx.AsyncBaseTransport):
    """Wraps an inner transport with retry semantics."""

    def __init__(self, inner: httpx.AsyncBaseTransport, config: RetryConfig) -> None:
        self._inner = inner
        self._config = config

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Per-request opt-out: callers signal "do not retry this one" via extensions.
        # Used by NotifierClient to skip retries on POST /dispatch without an idempotency key.
        if request.extensions.get("notifier_no_retry"):
            return await self._inner.handle_async_request(request)
        cfg = self._config
        last: httpx.Response | None = None
        for attempt in range(1, cfg.max_attempts + 1):
            response = await self._inner.handle_async_request(request)
            last = response
            should_retry, sleep_for = self._should_retry(response, attempt)
            if not should_retry:
                return response
            await response.aclose()
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        return last  # type: ignore[return-value]

    def _should_retry(self, response: httpx.Response, attempt: int) -> tuple[bool, float]:
        cfg = self._config
        if attempt >= cfg.max_attempts:
            return (False, 0.0)
        status = response.status_code
        if status in cfg.retry_on:
            return (True, cfg.backoff_base * (2 ** (attempt - 1)))
        if status == 429 and cfg.honor_retry_after:
            wait = parse_retry_after(response.headers.get("Retry-After"))
            return (True, wait if wait is not None else cfg.backoff_base * (2 ** (attempt - 1)))
        return (False, 0.0)

    async def aclose(self) -> None:
        await self._inner.aclose()
```

- [ ] **Step 4: Verify pass**

Run: `cd clients/python && uv run pytest tests/test_retry_config.py tests/test_retry_transport.py -v`
Expected: PASS — all 6 tests.

- [ ] **Step 5: Commit**

```bash
git add clients/python/src/notifier_client/retry.py \
        clients/python/tests/test_retry_config.py \
        clients/python/tests/test_retry_transport.py
git commit -m "#1 feat: RetryTransport with backoff + 429 Retry-After"
```

### Task 3.4: Idempotency-key helper

- [ ] **Step 1: Write tests**

`clients/python/tests/test_idempotency.py`:
```python
from notifier_client.idempotency import AUTO, resolve_idempotency_key


def test_explicit_value_passthrough():
    assert resolve_idempotency_key("watcher-evt-1") == "watcher-evt-1"


def test_none_returns_none():
    assert resolve_idempotency_key(None) is None


def test_auto_generates_ulid():
    key = resolve_idempotency_key(AUTO)
    assert isinstance(key, str)
    assert len(key) == 26    # ULID canonical form


def test_auto_generates_unique():
    a = resolve_idempotency_key(AUTO)
    b = resolve_idempotency_key(AUTO)
    assert a != b
```

- [ ] **Step 2: Verify fail**

Run: `cd clients/python && uv run pytest tests/test_idempotency.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement idempotency.py**

`clients/python/src/notifier_client/idempotency.py`:
```python
"""Idempotency-key helper.

The SDK lets callers pass:
- ``None`` — omit the header (UNSAFE under retry; the SDK never auto-retries
  ``POST /dispatch`` without a key)
- a string — passthrough
- ``AUTO`` sentinel — SDK generates a ULID

ULID is preferred over UUID for sortable, URL-safe, monotonic keys.
"""

from __future__ import annotations

from typing import Final

from ulid import ULID


class _AutoIdempotencyKey:
    """Sentinel — see module docstring."""

    _instance: "_AutoIdempotencyKey | None" = None

    def __new__(cls) -> "_AutoIdempotencyKey":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "AUTO"


AUTO: Final = _AutoIdempotencyKey()


def resolve_idempotency_key(value: str | _AutoIdempotencyKey | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, _AutoIdempotencyKey):
        return str(ULID())
    return value
```

- [ ] **Step 4: Verify pass**

Run: `cd clients/python && uv run pytest tests/test_idempotency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/python/src/notifier_client/idempotency.py \
        clients/python/tests/test_idempotency.py
git commit -m "#1 feat: idempotency-key helper with AUTO sentinel"
```

### Task 3.5: Redacting log filter

- [ ] **Step 1: Write tests**

`clients/python/tests/test_logging.py`:
```python
import logging

from notifier_client.logging import RedactingFilter


def test_filter_masks_api_key_in_message():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="auth header was nk_supersecret123 today", args=(), exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()
    assert "nk_***" in record.getMessage()


def test_filter_masks_in_args():
    flt = RedactingFilter(api_key="nk_supersecret123")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="key: %s", args=("nk_supersecret123",), exc_info=None,
    )
    flt.filter(record)
    assert "nk_supersecret123" not in record.getMessage()


def test_filter_no_op_when_no_key():
    flt = RedactingFilter(api_key=None)
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="hello", args=(), exc_info=None,
    )
    assert flt.filter(record) is True
    assert record.getMessage() == "hello"
```

- [ ] **Step 2: Verify fail**

Run: `cd clients/python && uv run pytest tests/test_logging.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement logging.py**

`clients/python/src/notifier_client/logging.py`:
```python
"""Logging support for notifier-client.

The SDK never emits logs on its own (callers wire their own loggers), but it
provides ``RedactingFilter`` so callers who do log the SDK's underlying httpx
traffic don't accidentally leak the X-API-Key.
"""

from __future__ import annotations

import logging


class RedactingFilter(logging.Filter):
    """Filter that masks the X-API-Key value in log messages and args."""

    def __init__(self, api_key: str | None) -> None:
        super().__init__()
        self._api_key = api_key
        self._mask = (api_key[:3] + "***") if api_key else None

    def filter(self, record: logging.LogRecord) -> bool:
        if self._api_key is None or self._mask is None:
            return True
        if isinstance(record.msg, str) and self._api_key in record.msg:
            record.msg = record.msg.replace(self._api_key, self._mask)
        if record.args:
            record.args = tuple(self._scrub(a) for a in record.args)   # type: ignore[assignment]
        return True

    def _scrub(self, value):
        if isinstance(value, str) and self._api_key in value:
            return value.replace(self._api_key, self._mask)
        return value
```

- [ ] **Step 4: Verify pass**

Run: `cd clients/python && uv run pytest tests/test_logging.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/python/src/notifier_client/logging.py \
        clients/python/tests/test_logging.py
git commit -m "#1 feat: RedactingFilter masks X-API-Key in logs"
```

### Task 3.6: NotifierClient facade

- [ ] **Step 1: Write tests**

`clients/python/tests/test_client.py`:
```python
import httpx
import pytest
import respx

from notifier_client import (
    AUTO,
    AuthError,
    NotifierClient,
    RateLimited,
    RetryConfig,
    ValidationError,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


@respx.mock
@pytest.mark.asyncio
async def test_health_round_trip(fast_retry):
    respx.get("https://t.local/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        result = await c.health()
    assert result == {"status": "ok"}


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_sends_x_api_key_header(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "k",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        })
    )
    async with NotifierClient(base_url="https://t.local", api_key="nk_secret", retry_config=fast_retry) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key="k",
        )
    assert route.calls.last.request.headers["X-API-Key"] == "nk_secret"


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_with_auto_idempotency_generates_ulid(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "auto",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        })
    )
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key=AUTO,
        )
    body = route.calls.last.request.read().decode()
    assert "idempotency_key" in body
    # ULIDs are 26 chars; check the value isn't empty or AUTO literal
    assert "AUTO" not in body


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_never_auto_retried_without_idempotency_key(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(503),
    )
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        with pytest.raises(Exception):    # ServerError
            await c.dispatch(
                title_template="T", body_template="B", channel_ids=["ch1"],
                idempotency_key=None,
            )
    # Should have been called exactly once — no retries on POST /dispatch without idempotency_key
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_dispatch_retried_with_idempotency_key(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(side_effect=[
        httpx.Response(503),
        httpx.Response(202, json={
            "id": "01H...", "tenant_id": "t1", "template_id": None, "idempotency_key": "k",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        }),
    ])
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key="k",
        )
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_validation_error_with_field_path(fast_retry):
    respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(422, json={"detail": {
            "section": "variables", "path": "strain", "message": "required",
        }})
    )
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        with pytest.raises(ValidationError) as exc:
            await c.dispatch(
                title_template="T", body_template="B", channel_ids=["ch1"],
                idempotency_key="k",
            )
    assert exc.value.field_path == "strain"
    assert exc.value.section == "variables"


@respx.mock
@pytest.mark.asyncio
async def test_auth_error_on_401(fast_retry):
    respx.get("https://t.local/health").mock(return_value=httpx.Response(401))
    async with NotifierClient(base_url="https://t.local", api_key="bad", retry_config=fast_retry) as c:
        with pytest.raises(AuthError):
            await c.health()


@respx.mock
@pytest.mark.asyncio
async def test_rate_limited_when_429_exhausted(fast_retry):
    # max_attempts=2; both 429 → final response surfaces as RateLimited
    respx.get("https://t.local/health").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )
    async with NotifierClient(base_url="https://t.local", api_key="nk_x", retry_config=fast_retry) as c:
        with pytest.raises(RateLimited) as exc:
            await c.health()
    assert exc.value.retry_after_seconds == 0.0


def test_repr_redacts_api_key():
    c = NotifierClient(base_url="https://t.local", api_key="nk_supersecret")
    assert "nk_supersecret" not in repr(c)
    assert "nk_***" in repr(c)
```

- [ ] **Step 2: Verify fail**

Run: `cd clients/python && uv run pytest tests/test_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement client.py**

`clients/python/src/notifier_client/client.py`:
```python
"""``NotifierClient`` — the public facade.

Composes the generated client (for typed models) with our own httpx layer
(for retries, auth, error mapping). We do *not* subclass anything in
``generated/`` — codegen renames internals between versions of
``openapi-python-client``.

The client is async-only. A sync facade is not in scope; if you need one,
file an issue with a use case.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from notifier_client.errors import NotifierError, error_from_response
from notifier_client.idempotency import AUTO, _AutoIdempotencyKey, resolve_idempotency_key
from notifier_client.retry import RetryConfig, RetryTransport


class NotifierClient:
    """Async client for the notifier service."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        retry_config: RetryConfig | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._retry_config = retry_config or RetryConfig()
        self._mask = (api_key[:3] + "***") if api_key else "***"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            transport=RetryTransport(httpx.AsyncHTTPTransport(), self._retry_config),
        )

    def __repr__(self) -> str:
        return f"NotifierClient(base_url={self._base_url!r}, api_key={self._mask!r})"

    async def __aenter__(self) -> "NotifierClient":
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None,
                        exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- endpoints ---

    async def health(self) -> dict[str, Any]:
        return await self._json_request("GET", "/health", retry_safe=True)

    async def ready(self) -> dict[str, Any]:
        return await self._json_request("GET", "/ready", retry_safe=True)

    async def dispatch(
        self,
        *,
        template_id: str | None = None,
        title_template: str | None = None,
        body_template: str | None = None,
        variables: dict[str, Any] | None = None,
        channel_ids: list[str],
        idempotency_key: str | _AutoIdempotencyKey | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /api/v1/dispatch.

        Auto-retries are only attempted when ``idempotency_key`` is non-None
        (including ``AUTO``). Without a key, retrying is unsafe and the SDK
        will surface the first failure.
        """
        resolved_key = resolve_idempotency_key(idempotency_key)
        body: dict[str, Any] = {
            "channel_ids": channel_ids,
            "variables": variables or {},
            "metadata": metadata or {},
        }
        if template_id is not None:
            body["template_id"] = template_id
        if title_template is not None:
            body["title_template"] = title_template
        if body_template is not None:
            body["body_template"] = body_template
        if resolved_key is not None:
            body["idempotency_key"] = resolved_key
        return await self._json_request(
            "POST", "/api/v1/dispatch", json=body,
            retry_safe=resolved_key is not None,
        )

    # --- internals ---

    async def _json_request(
        self, method: str, path: str, *, json: Any = None, retry_safe: bool,
    ) -> dict[str, Any]:
        extensions = {} if retry_safe else {"notifier_no_retry": True}
        response = await self._http.request(method, path, json=json, extensions=extensions)
        if response.status_code >= 400:
            raise error_from_response(response)
        if not response.content:
            return {}
        return response.json()
```

- [ ] **Step 4: Update __init__.py to re-export the public surface**

`clients/python/src/notifier_client/__init__.py`:
```python
"""notifier-client — async Python SDK for the notifier service.

Pinned 1:1 with notifier server version. See README for usage.
"""

from notifier_client.client import NotifierClient
from notifier_client.errors import (
    AuthError,
    NotifierError,
    RateLimited,
    ServerError,
    ValidationError,
)
from notifier_client.idempotency import AUTO
from notifier_client.logging import RedactingFilter
from notifier_client.retry import RetryConfig

__version__ = "0.1.0"

__all__ = [
    "AUTO",
    "AuthError",
    "NotifierClient",
    "NotifierError",
    "RateLimited",
    "RedactingFilter",
    "RetryConfig",
    "ServerError",
    "ValidationError",
    "__version__",
]
```

- [ ] **Step 5: Run all SDK unit tests**

Run: `cd clients/python && uv run pytest -v`
Expected: PASS — all tests across `test_errors`, `test_retry_after`, `test_retry_config`, `test_retry_transport`, `test_idempotency`, `test_logging`, `test_client` (~25–30 tests).

- [ ] **Step 6: Run ruff**

Run: `cd clients/python && uv run ruff check .`
Expected: clean (or trivially fixable).

- [ ] **Step 7: Commit**

```bash
git add clients/python/src/notifier_client/client.py \
        clients/python/src/notifier_client/__init__.py \
        clients/python/tests/test_client.py
git commit -m "#1 feat: NotifierClient facade with auth, retries, idempotency"
```

---

## PR 4 — Integration smoke test

**Files:**
- Create: [clients/python/tests/conftest.py](clients/python/tests/conftest.py)
- Create: [clients/python/tests/test_smoke_integration.py](clients/python/tests/test_smoke_integration.py)

### Task 4.1: Add a tenant fixture that uses scripts/seed_tenant.py

- [ ] **Step 1: Inspect the existing seed script**

Read [scripts/seed_tenant.py](scripts/seed_tenant.py) — it prints `tenant_id=...` and `raw_key=...` on stdout.

- [ ] **Step 2: Write the conftest fixture**

`clients/python/tests/conftest.py`:
```python
"""Shared fixtures for SDK tests."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
NOTIFIER_URL = os.environ.get("NOTIFIER_URL", "http://localhost:9001")


@pytest.fixture(scope="session")
def notifier_url() -> str:
    return NOTIFIER_URL


@pytest.fixture(scope="session")
def tenant_credentials() -> tuple[str, str]:
    """Provision a tenant + API key via scripts/seed_tenant.py.

    Skips integration tests if the seed script can't run (e.g. no DB env)."""
    if os.environ.get("NOTIFIER_TENANT_ID") and os.environ.get("NOTIFIER_API_KEY"):
        return os.environ["NOTIFIER_TENANT_ID"], os.environ["NOTIFIER_API_KEY"]
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "seed_tenant.py"),
             "sdk-integration", "smoke"],
            capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"could not seed tenant: {exc}")
    out = result.stdout
    tid = re.search(r"tenant_id=(\S+)", out)
    key = re.search(r"raw_key=(\S+)", out)
    if not (tid and key):
        pytest.skip(f"seed script output unparseable: {out!r}")
    return tid.group(1), key.group(1)
```

### Task 4.2: Write the integration smoke test

- [ ] **Step 1: Write the test**

`clients/python/tests/test_smoke_integration.py`:
```python
"""Integration smoke test against a live notifier on $NOTIFIER_URL (default :9001).

Requires:
- A notifier server reachable at $NOTIFIER_URL
- Either ($NOTIFIER_TENANT_ID + $NOTIFIER_API_KEY) provided, or the seed script
  is runnable from the repo root.

Per AGENTS.md, port 9000 belongs to systemd. Default for SDK dev tests is 9001.
"""

import pytest

from notifier_client import AUTO, NotifierClient


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_health_endpoint(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        result = await c.health()
    assert result.get("status") == "ok"


@pytest.mark.asyncio
async def test_inline_dispatch_with_auto_idempotency(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        # Skipped if the tenant has no channels — smoke covers the auth + render path.
        with pytest.raises(Exception) as exc:
            await c.dispatch(
                title_template="hello {{ who }}",
                body_template="body {{ who }}",
                variables={"who": "world"},
                channel_ids=["00000000000000000000000000"],   # bogus, will 404
                idempotency_key=AUTO,
            )
        # Expecting a 404 NotifierError — channel not found. The point is the
        # request reached the server and the auth worked.
        assert "404" in str(exc.value) or "not found" in str(exc.value).lower()
```

- [ ] **Step 2: Verify it runs (or skips cleanly) when no notifier is running**

Run: `cd clients/python && uv run pytest -m integration -v`
Expected: SKIP (cleanly, with a clear "could not seed tenant" or connection-refused message), or PASS if a notifier is running on :9001.

- [ ] **Step 3: Run a real smoke check**

In a separate terminal:
```bash
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 9001 --reload
```

Then:
```bash
cd clients/python && uv run pytest -m integration -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add clients/python/tests/conftest.py clients/python/tests/test_smoke_integration.py
git commit -m "#1 test: integration smoke test against localhost:9001"
```

---

## PR 5 — Watcher consumer (in the watcher repo, not here)

This PR lives in [CannObserv/watcher](https://github.com/CannObserv/watcher). Out of scope for this plan beyond noting:

- Tag a `v0.1.0` release on notifier (after PRs 1–4 merge).
- Watcher adds: `uv add "notifier-client @ git+ssh://git@github.com/CannObserv/notifier.git@v0.1.0#subdirectory=clients/python"`.
- Watcher swaps its hand-written notifier calls (if any) to `NotifierClient`.
- Watcher PR closes [CannObserv/watcher#132](https://github.com/CannObserv/watcher/issues/132).

When that watcher PR merges, this notifier issue (#1) can be closed with a comment linking to the watcher PR.

---

## Known limitations / follow-ups (post-v0.1.0)

- **Typed return values.** `NotifierClient.dispatch()` returns `dict[str, Any]` rather than a typed model from `generated/`. v0.1 prioritizes the wrapper behaviors (auth, retries, idempotency, errors); typed returns can be added in v0.2 by importing the generated `DispatchOut` model and deserializing into it. The OpenAPI source-of-truth is already in place.
- **Other endpoints.** v0.1 wires `health`, `ready`, and `dispatch`. Templates, channels, preview, and `apprise/plugins` are reachable via the generated client directly; the facade can grow methods for them in v0.2 as watcher's needs surface.
- **Other-language clients.** `clients/typescript/` etc. are deliberately not stubbed. Empty directories rot.
- **PyPI publishing.** Deferred. v0 installs from a git tag.

## Verification checklist (run before requesting review on the final PR)

- [ ] All unit tests pass: `cd clients/python && uv run pytest -v`
- [ ] Integration smoke passes against a real notifier on :9001
- [ ] `uv run ruff check clients/python/` is clean
- [ ] `clients/python/scripts/regen.sh` is idempotent (run twice, no diff)
- [ ] CI workflow file lints (`actionlint .github/workflows/sdk-staleness.yml` if available; otherwise visual review)
- [ ] `__repr__` of `NotifierClient` does not contain the API key
- [ ] `pyproject.toml` `version` matches notifier's `pyproject.toml` `version` (both `0.1.0`)
- [ ] README example imports actually work
