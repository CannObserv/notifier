# notifier-client

Async Python SDK for the [notifier](https://github.com/CannObserv/notifier) service.

## Install

```bash
uv add "notifier-client @ git+ssh://git@github.com/CannObserv/notifier.git@v0.2.0#subdirectory=clients/python"
```

Versions are pinned 1:1 with the notifier server. SDK `0.x.y` ⇔ notifier `0.x.y`.

See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## Usage

```python
from notifier_client import NotifierClient

async with NotifierClient(base_url="https://notifier.exe.xyz", api_key="nk_...") as client:
    ch = await client.channels.create(name="ops", apprise_url="slack://...")
    print(ch.id, ch.apprise_url_masked)

    test_result = await client.channels.send_test(ch.id)
    print("test:", test_result.success, test_result.reason)

    tpl = await client.templates.create(
        name="alert", title_template="{{ event }}", body_template="...",
    )

    result = await client.dispatch(
        template_id=tpl.id,
        variables={"event": "fire"},
        channel_ids=[ch.id],
        idempotency_key="evt-1",
    )
    print(result.status, [a.status for a in result.attempts])

    # result.status is DispatchOutStatus; a.status is DispatchAttemptOutStatus.
    # Both are str subclasses, so string comparison works either way:
    from notifier_client import DispatchOutStatus, DispatchAttemptOutStatus
    if result.status == DispatchOutStatus.SUCCEEDED:
        print("all channels delivered")
    elif result.status == DispatchOutStatus.PARTIAL:
        failed = [a for a in result.attempts if a.status == DispatchAttemptOutStatus.FAILED]
        print(f"{len(failed)} channel(s) failed:", [a.channel_id for a in failed])
```

### Working with dispatch results

`result.status` is a `DispatchOutStatus` enum with values `SUCCEEDED`, `PARTIAL`, and `FAILED`. Each `result.attempts[n].status` is a `DispatchAttemptOutStatus` with values `SUCCEEDED` and `FAILED`. Both inherit from `str`, so `result.status == "succeeded"` works alongside the enum form.

### Sub-clients

- `client.channels.{list, create, get, update, delete, send_test}` → `ChannelOut` / `ChannelTestResponse`
- `client.templates.{list, create, get, update, delete, preview}` → `TemplateOut` / `TemplatePreviewResponse`
- `client.preview(*, title_template, body_template, variables, variables_schema=None)` → `PreviewResponse` (stateless inline render; rendering failures return 200 OK with `.error` populated, no exception)
- `client.apprise.{list_plugins, get_plugin, assemble}` → `PluginListItem` / `PluginDetail` / `AssembleResponse`

`client.dispatch(...)` returns `DispatchOut`. `client.health()` and `client.ready()` continue to return `dict[str, Any]` because the server's response is a free-form key/value bag.

### Idempotency

`POST /dispatch` is auto-retried on 5xx and network errors **only when `idempotency_key` is non-None**. Three call shapes:

| `idempotency_key=` | Behavior |
|---|---|
| `"some-string"` | Server-side dedupe per `(tenant_id, key)`; SDK auto-retries on transient failures |
| `AUTO` | SDK generates a ULID; same retry semantics as the explicit string |
| `None` *(default)* | Field omitted from request body; SDK does **not** auto-retry — first failure surfaces immediately |

### Retry tuning

```python
from notifier_client import NotifierClient, RetryConfig

retry = RetryConfig(
    max_attempts=5,                          # default 3
    backoff_base=0.25,                       # exponential: base * 2^(attempt-1)
    retry_on=frozenset({500, 502, 503, 504}),  # default
    honor_retry_after=True,                  # honor 429 Retry-After header
    retry_on_network_error=True,             # retry httpx.TransportError (timeouts, conn errors)
)
async with NotifierClient(
    base_url=..., api_key=...,
    retry_config=retry,
    timeout=30.0,                            # per-request timeout in seconds; default 10.0
) as client:
    ...
```

### Errors

All SDK errors inherit `NotifierError`. Catch the base, or branch on the typed subclass:

```python
from notifier_client import (
    AuthError,         # 401, 403
    NotifierError,     # base — also catches 404 and other 4xx
    RateLimited,       # 429 after retries are exhausted; carries .retry_after_seconds
    ServerError,       # 5xx after retries are exhausted
    ValidationError,   # 422; carries .field_path and .section
)

try:
    await client.dispatch(...)
except ValidationError as e:
    log.warning("notifier rejected request: %s at %s", e, e.field_path)
except RateLimited as e:
    log.warning("notifier rate-limited; back off for %s", e.retry_after_seconds)
```

### Logging

The SDK emits no logs of its own. If you log httpx traffic and want to mask the API key:

```python
import logging
from notifier_client import RedactingFilter

logging.getLogger("httpx").addFilter(RedactingFilter(api_key="nk_..."))
```

## Development

This package is co-located with the notifier server in [CannObserv/notifier](https://github.com/CannObserv/notifier). The `generated/` subdirectory is regenerated from `app.openapi()` — never edit by hand. See [PR #1](https://github.com/CannObserv/notifier/issues/1).

### Integration tests

Integration tests are gated on `TEST_DATABASE_URL`. The fixture creates the
schema in that DB, spawns a uvicorn subprocess wired to it on an ephemeral
port, seeds a tenant, and drops the schema on session teardown. Every
subprocess receives `DATABASE_URL=$TEST_DATABASE_URL`, so production cannot
be polluted even if `/etc/notifier/.env` is exported into the parent shell.

```bash
export $(cat /etc/notifier/.env .env 2>/dev/null | xargs)
uv run pytest -m integration
```

Skips with a message if `TEST_DATABASE_URL` is not set.
