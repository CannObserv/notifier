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
