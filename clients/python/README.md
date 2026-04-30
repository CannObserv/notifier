# notifier-client

Async Python SDK for the [notifier](https://github.com/CannObserv/notifier) service.

## Install

```bash
uv add "notifier-client @ git+ssh://git@github.com/CannObserv/notifier.git@v0.1.0#subdirectory=clients/python"
```

Versions are pinned 1:1 with the notifier server. SDK `0.x.y` ⇔ notifier `0.x.y`.

## Usage

```python
from notifier_client import AUTO, NotifierClient

async with NotifierClient(base_url="https://notifier.exe.xyz", api_key="nk_...") as client:
    result = await client.dispatch(
        template_id="...",
        variables={"strain": "Blue Dream"},
        channel_ids=["..."],
        idempotency_key="watcher-event-1234",   # or AUTO to auto-generate a ULID
    )
```

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
