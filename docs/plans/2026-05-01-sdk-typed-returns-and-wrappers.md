# SDK typed returns + wrapper methods (channels / templates / preview / apprise) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle GitHub issue #3 (SDK wrapper methods for `channels`, `templates`, stateless `preview`, `apprise`) with the v0.2 typed-returns sweep. Ship a single coherent SDK 0.2.0 where every endpoint method returns a typed model from `notifier_client.types` (re-exported from `generated/`) — no hybrid dict/typed surface.

**Architecture:**
- New public module `notifier_client/types.py` re-exports the generated `attrs` classes (`ChannelOut`, `TemplateOut`, `DispatchOut`, `PluginListItem`, `PluginDetail`, `AssembleResponse`, `PreviewResponse`, `TemplatePreviewResponse`, `ChannelTestResponse`) under stable public names. A surface test guards those names against codegen renames.
- `NotifierClient._typed_request[T](method, path, *, model: type[T], json=..., retry_safe: bool) -> T` is the single entry point that runs auth + retry + error-mapping then `model.from_dict(response.json())`. Everything routes through it.
- Sub-clients (`ChannelsAPI`, `TemplatesAPI`, `AppriseAPI`) are thin facades that hold a `NotifierClient` reference and expose namespaced methods. They never own state. Top-level `client.dispatch()`, `client.preview()`, `client.health()`, `client.ready()` stay on `NotifierClient` itself.
- `health()` and `ready()` are the lone exception to typed returns: their server-side schema is an open dict (`{"status": "ok", ...}`); the generated class is just an `additional_properties` bag. We keep `dict[str, Any]` there and document why.
- No back-compat shims. Pre-production. Bump SDK to 0.2.0; do not bump notifier server unless schema regen forces it.

**Tech Stack:** Python 3.12, `httpx>=0.28`, `attrs` (via `openapi-python-client` codegen), `respx` for unit tests, real Postgres via `TEST_DATABASE_URL` for integration.

**Issue reference:** GitHub issue [#3](https://github.com/CannObserv/notifier/issues/3). User has approved option (b) (typed from day one) and waived back-compat / data preservation. PKs are already ULID — no schema work.

---

## File Structure

### Created
- `clients/python/src/notifier_client/types.py` — public type surface (re-exports + module-level `__all__`).
- `clients/python/src/notifier_client/sub_clients/__init__.py` — namespace package for sub-clients.
- `clients/python/src/notifier_client/sub_clients/channels.py` — `ChannelsAPI`.
- `clients/python/src/notifier_client/sub_clients/templates.py` — `TemplatesAPI`.
- `clients/python/src/notifier_client/sub_clients/apprise.py` — `AppriseAPI`.
- `clients/python/tests/test_types_surface.py` — guards public type names + minimal field shape.
- `clients/python/tests/test_channels_api.py` — respx unit tests for `ChannelsAPI`.
- `clients/python/tests/test_templates_api.py` — respx unit tests for `TemplatesAPI`.
- `clients/python/tests/test_preview_api.py` — respx unit tests for top-level `client.preview()`.
- `clients/python/tests/test_apprise_api.py` — respx unit tests for `AppriseAPI`.
- `clients/python/tests/test_channels_integration.py` — integration round-trip (channel create → dispatch → channel delete).
- `clients/python/CHANGELOG.md` — new file documenting v0.2.0 break.

### Modified
- `clients/python/src/notifier_client/__init__.py` — re-export new types + sub-clients; bump version.
- `clients/python/src/notifier_client/client.py` — add `_typed_request[T]`, migrate `dispatch()` return type, attach sub-client instances.
- `clients/python/tests/test_client.py` — update existing tests to assert `DispatchOut` instances instead of dict shape.
- `clients/python/tests/test_smoke_integration.py` — update existing assertions for typed return where applicable (health stays dict).
- `clients/python/pyproject.toml` — bump `version = "0.2.0"`.
- `clients/python/README.md` — replace dict-shape examples with typed examples; add sub-client section; reference `CHANGELOG.md`.

### Untouched
- `generated/` — never hand-edit; only regen via `clients/python/scripts/regen.sh` if schema changes (none expected).
- `client.py` retry/error/auth mechanics and the `RetryTransport`/`RetryConfig`/`AUTO`/`RedactingFilter` modules — already correct.
- Server code under `src/api/` — schema is stable for this work.

---

## Stage 1: Public type surface

**Why first:** every later stage imports from `notifier_client.types`. Locking the public names down up front prevents Stage 3–6 from re-naming things mid-flight.

**Files:**
- Create: `clients/python/src/notifier_client/types.py`
- Create: `clients/python/tests/test_types_surface.py`
- Modify: `clients/python/src/notifier_client/__init__.py`

### Tasks

- [ ] **Step 1.1: Write the failing surface test**

Create `clients/python/tests/test_types_surface.py`:

```python
"""Lock the public type surface against codegen renames.

The generated/ subtree may rename internal classes between
openapi-python-client versions. notifier_client.types is the stable public
import path; this test breaks at PR time (not at consumer-pin time) if a
public name disappears.
"""

import pytest


def test_public_type_names_importable():
    from notifier_client.types import (
        AssembleResponse,
        ChannelOut,
        ChannelTestResponse,
        DispatchOut,
        PluginDetail,
        PluginListItem,
        PreviewResponse,
        TemplateOut,
        TemplatePreviewResponse,
    )
    # Each must be a class, not a module
    for cls in (AssembleResponse, ChannelOut, ChannelTestResponse, DispatchOut,
                PluginDetail, PluginListItem, PreviewResponse, TemplateOut,
                TemplatePreviewResponse):
        assert isinstance(cls, type)
        assert hasattr(cls, "from_dict")
        assert hasattr(cls, "to_dict")


def test_channel_out_has_expected_fields():
    from notifier_client.types import ChannelOut
    out = ChannelOut.from_dict({
        "id": "01H", "tenant_id": "t1", "name": "n",
        "apprise_url_masked": "m", "channel_hint": None,
        "created_at": "2026-04-30T00:00:00Z",
        "updated_at": "2026-04-30T00:00:00Z",
    })
    assert out.id == "01H"
    assert out.tenant_id == "t1"
    assert out.name == "n"


def test_dispatch_out_has_expected_fields():
    from notifier_client.types import DispatchOut
    out = DispatchOut.from_dict({
        "id": "01H", "tenant_id": "t1", "template_id": None,
        "idempotency_key": None, "rendered_title": "T", "rendered_body": "B",
        "status": "succeeded", "metadata": {}, "attempts": [],
        "created_at": "2026-04-30T00:00:00Z",
    })
    assert out.id == "01H"
    assert out.status == "succeeded"
    assert out.attempts == []


def test_top_level_init_re_exports_types():
    """Common types should also be available as `from notifier_client import ...`."""
    import notifier_client
    assert hasattr(notifier_client, "ChannelOut")
    assert hasattr(notifier_client, "TemplateOut")
    assert hasattr(notifier_client, "DispatchOut")
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd clients/python && uv run pytest tests/test_types_surface.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'notifier_client.types'`.

- [ ] **Step 1.3: Create the public types module**

Create `clients/python/src/notifier_client/types.py`:

```python
"""Public type surface for notifier-client.

Stable import path for the typed response/request models. Backed by classes
in ``notifier_client.generated``, which can be renamed between codegen
versions; this module insulates consumers from that churn.

Add a name here only when an endpoint method returns or accepts the type.
The surface test (``tests/test_types_surface.py``) guards every name listed
in ``__all__``.
"""

from __future__ import annotations

from notifier_client.generated.models.assemble_response import AssembleResponse
from notifier_client.generated.models.channel_out import ChannelOut
from notifier_client.generated.models.channel_test_response import ChannelTestResponse
from notifier_client.generated.models.dispatch_out import DispatchOut
from notifier_client.generated.models.plugin_detail import PluginDetail
from notifier_client.generated.models.plugin_list_item import PluginListItem
from notifier_client.generated.models.preview_response import PreviewResponse
from notifier_client.generated.models.template_out import TemplateOut
from notifier_client.generated.models.template_preview_response import TemplatePreviewResponse

__all__ = [
    "AssembleResponse",
    "ChannelOut",
    "ChannelTestResponse",
    "DispatchOut",
    "PluginDetail",
    "PluginListItem",
    "PreviewResponse",
    "TemplateOut",
    "TemplatePreviewResponse",
]
```

- [ ] **Step 1.4: Re-export the most-used types from the package root**

Modify `clients/python/src/notifier_client/__init__.py` — append to imports and `__all__`:

```python
from notifier_client.types import (
    AssembleResponse,
    ChannelOut,
    ChannelTestResponse,
    DispatchOut,
    PluginDetail,
    PluginListItem,
    PreviewResponse,
    TemplateOut,
    TemplatePreviewResponse,
)
```

Add each name to the existing `__all__` list (alphabetically).

- [ ] **Step 1.5: Run the surface test to verify it passes**

```bash
cd clients/python && uv run pytest tests/test_types_surface.py -v
```
Expected: PASS (4 tests).

- [ ] **Step 1.6: Run the entire SDK suite to verify no regression**

```bash
cd clients/python && uv run pytest
```
Expected: PASS (existing 44 tests + 4 new).

- [ ] **Step 1.7: Commit**

```bash
git add clients/python/src/notifier_client/types.py \
        clients/python/src/notifier_client/__init__.py \
        clients/python/tests/test_types_surface.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk): add notifier_client.types public surface

Stable re-exports of generated attrs models. Surface test guards public
names against openapi-python-client renames.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 1 acceptance
- `from notifier_client.types import ChannelOut, ...` works for all nine names.
- `from notifier_client import ChannelOut, TemplateOut, DispatchOut` works.
- Surface test passes.
- Existing test suite still green.

---

## Stage 2: `_typed_request[T]` helper + migrate `dispatch()` to typed returns

**Why second:** establishes the pattern Stages 3–6 will follow. Migrating `dispatch()` proves the helper works on the most complex existing method before we copy-paste the shape into sub-clients.

**Files:**
- Modify: `clients/python/src/notifier_client/client.py`
- Modify: `clients/python/tests/test_client.py`

### Tasks

- [ ] **Step 2.1: Update existing dispatch tests to expect typed return**

Modify `clients/python/tests/test_client.py`:

Replace `test_dispatch_sends_x_api_key_header` body to assert `isinstance(result, DispatchOut)` after the dispatch call. Add the import:

```python
from notifier_client import DispatchOut
```

Replace `test_dispatch_sends_x_api_key_header`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_dispatch_sends_x_api_key_header_and_returns_typed(fast_retry):
    route = respx.post("https://t.local/api/v1/dispatch").mock(
        return_value=httpx.Response(202, json={
            "id": "01HABCDEFGHJKMNPQRSTVWXYZ0", "tenant_id": "t1",
            "template_id": None, "idempotency_key": "k",
            "rendered_title": "T", "rendered_body": "B", "status": "succeeded",
            "metadata": {}, "created_at": "2026-04-30T00:00:00Z", "attempts": [],
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_secret", retry_config=fast_retry
    ) as c:
        result = await c.dispatch(
            title_template="T", body_template="B", channel_ids=["ch1"],
            idempotency_key="k",
        )
    assert route.calls.last.request.headers["X-API-Key"] == "nk_secret"
    assert isinstance(result, DispatchOut)
    assert result.id == "01HABCDEFGHJKMNPQRSTVWXYZ0"
    assert result.status == "succeeded"
```

Add a new test `test_dispatch_health_still_returns_dict` to lock in the documented exception:

```python
@respx.mock
@pytest.mark.asyncio
async def test_health_returns_dict(fast_retry):
    respx.get("https://t.local/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "build_id": "abc"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.health()
    assert isinstance(result, dict)
    assert result["status"] == "ok"
```

- [ ] **Step 2.2: Run the updated tests to verify they fail**

```bash
cd clients/python && uv run pytest tests/test_client.py::test_dispatch_sends_x_api_key_header_and_returns_typed -v
```
Expected: FAIL with `assert isinstance(result, DispatchOut)` — `result` is currently a dict.

- [ ] **Step 2.3: Add the `_typed_request[T]` helper and migrate `dispatch()`**

Modify `clients/python/src/notifier_client/client.py`:

Add a `TypeVar` import at the top:

```python
from typing import Any, TypeVar
```

Add a `Protocol`-style generic:

```python
T = TypeVar("T")
```

Add the `_typed_request` method directly after `_json_request`:

```python
async def _typed_request(
    self, method: str, path: str, *, model: type[T],
    json: Any = None, retry_safe: bool,
) -> T:
    """Run an authed request, map errors, and parse into ``model``.

    The single funnel for all typed endpoint methods. ``model.from_dict``
    must accept the JSON body verbatim.
    """
    extensions = {} if retry_safe else {"notifier_no_retry": True}
    response = await self._http.request(method, path, json=json, extensions=extensions)
    if response.status_code >= 400:
        raise error_from_response(response)
    return model.from_dict(response.json())
```

Update the import block:

```python
from notifier_client.types import DispatchOut
```

Change the `dispatch` signature return type and body:

```python
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
) -> DispatchOut:
    # ... existing body construction unchanged ...
    return await self._typed_request(
        "POST", "/api/v1/dispatch", json=body,
        model=DispatchOut, retry_safe=resolved_key is not None,
    )
```

Update the docstring `Returns:` block to read:

```
A ``DispatchOut`` (typed). ``.id``, ``.status``, ``.rendered_title``,
``.rendered_body``, ``.attempts`` are populated; ``.idempotency_key``
echoes the request value (or is ``None`` if omitted).
```

Leave `health()` and `ready()` returning `dict[str, Any]` via `_json_request`. Add an inline comment at each:

```python
async def health(self) -> dict[str, Any]:
    # Free-form server schema; no typed model worth wrapping.
    return await self._json_request("GET", "/health", retry_safe=True)
```

- [ ] **Step 2.4: Run the dispatch tests to verify they pass**

```bash
cd clients/python && uv run pytest tests/test_client.py -v
```
Expected: PASS (all tests in the file).

- [ ] **Step 2.5: Run the full SDK suite**

```bash
cd clients/python && uv run pytest
```
Expected: PASS.

- [ ] **Step 2.6: Lint check**

```bash
cd clients/python && uv run ruff check .
```
Expected: PASS.

- [ ] **Step 2.7: Commit**

```bash
git add clients/python/src/notifier_client/client.py clients/python/tests/test_client.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk)!: dispatch() returns DispatchOut; add _typed_request helper

BREAKING: dispatch() now returns a DispatchOut attrs model instead of
dict[str, Any]. health() and ready() retain dict — server schema is
free-form there.

_typed_request[T] is the single funnel; sub-clients in subsequent stages
route through it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 2 acceptance
- `dispatch()` returns `DispatchOut`.
- `health()`/`ready()` still return dict (documented exception).
- All 5xx/429/422/AUTO/no-key/idempotency tests still green.
- `_typed_request` is the only path that calls `from_dict`.

---

## Stage 3: `client.channels.*` sub-client

**Files:**
- Create: `clients/python/src/notifier_client/sub_clients/__init__.py` (empty namespace marker; module docstring only)
- Create: `clients/python/src/notifier_client/sub_clients/channels.py`
- Create: `clients/python/tests/test_channels_api.py`
- Create: `clients/python/tests/test_channels_integration.py`
- Modify: `clients/python/src/notifier_client/client.py` (attach `self.channels = ChannelsAPI(self)`)

### Tasks

- [ ] **Step 3.1: Write failing unit tests for `ChannelsAPI`**

Create `clients/python/tests/test_channels_api.py`:

```python
import httpx
import pytest
import respx

from notifier_client import ChannelOut, ChannelTestResponse, NotifierClient, RetryConfig


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


_CHANNEL_BODY = {
    "id": "01HA", "tenant_id": "t1", "name": "ops",
    "apprise_url_masked": "slack://***", "channel_hint": "slack",
    "created_at": "2026-04-30T00:00:00Z",
    "updated_at": "2026-04-30T00:00:00Z",
}


@respx.mock
@pytest.mark.asyncio
async def test_channels_list_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(200, json=[_CHANNEL_BODY])
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.list()
    assert len(result) == 1
    assert isinstance(result[0], ChannelOut)
    assert result[0].name == "ops"


@respx.mock
@pytest.mark.asyncio
async def test_channels_create_sends_body_and_returns_typed(fast_retry):
    route = respx.post("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(201, json=_CHANNEL_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.create(
            name="ops", apprise_url="slack://hook/AAA/BBB", channel_hint="slack",
        )
    body = route.calls.last.request.read().decode()
    assert "slack://hook/AAA/BBB" in body
    assert isinstance(result, ChannelOut)


@respx.mock
@pytest.mark.asyncio
async def test_channels_get_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(200, json=_CHANNEL_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.get("01HA")
    assert isinstance(result, ChannelOut)
    assert result.id == "01HA"


@respx.mock
@pytest.mark.asyncio
async def test_channels_update_patches_and_returns_typed(fast_retry):
    route = respx.patch("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(200, json={**_CHANNEL_BODY, "name": "renamed"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.update("01HA", name="renamed")
    body = route.calls.last.request.read().decode()
    assert "renamed" in body
    assert "apprise_url" not in body  # only supplied fields are sent
    assert result.name == "renamed"


@respx.mock
@pytest.mark.asyncio
async def test_channels_delete_returns_none(fast_retry):
    respx.delete("https://t.local/api/v1/channels/01HA").mock(
        return_value=httpx.Response(204)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.delete("01HA")
    assert result is None


@respx.mock
@pytest.mark.asyncio
async def test_channels_test_returns_typed(fast_retry):
    respx.post("https://t.local/api/v1/channels/01HA/test").mock(
        return_value=httpx.Response(200, json={"success": True, "reason": "ok"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.channels.test("01HA")
    assert isinstance(result, ChannelTestResponse)
    assert result.success is True


@respx.mock
@pytest.mark.asyncio
async def test_channels_create_validation_error(fast_retry):
    from notifier_client import ValidationError
    respx.post("https://t.local/api/v1/channels").mock(
        return_value=httpx.Response(422, json={"detail": [
            {"loc": ["body", "apprise_url"], "msg": "field required", "type": "missing"}
        ]})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ValidationError) as exc:
            await c.channels.create(name="ops", apprise_url="")
    assert exc.value.field_path == "body.apprise_url"
```

- [ ] **Step 3.2: Run unit tests to verify they fail**

```bash
cd clients/python && uv run pytest tests/test_channels_api.py -v
```
Expected: FAIL with `AttributeError: 'NotifierClient' object has no attribute 'channels'`.

- [ ] **Step 3.3: Implement the `ChannelsAPI` sub-client**

Create `clients/python/src/notifier_client/sub_clients/__init__.py`:

```python
"""Sub-clients for the notifier API.

Each sub-client is a thin facade over ``NotifierClient._typed_request``.
They never own state; they hold a reference to the parent client.
"""
```

Create `clients/python/src/notifier_client/sub_clients/channels.py`:

```python
"""``client.channels.*`` — channel CRUD + test."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notifier_client.errors import error_from_response
from notifier_client.generated.models.channel_create import ChannelCreate
from notifier_client.generated.models.channel_update import ChannelUpdate
from notifier_client.generated.types import UNSET, Unset
from notifier_client.types import ChannelOut, ChannelTestResponse

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class ChannelsAPI:
    """Channel CRUD + test under ``/api/v1/channels``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list(self) -> list[ChannelOut]:
        """GET /api/v1/channels — all channels owned by the calling tenant."""
        response = await self._client._http.request("GET", "/api/v1/channels")
        if response.status_code >= 400:
            raise error_from_response(response)
        return [ChannelOut.from_dict(item) for item in response.json()]

    async def create(
        self, *, name: str, apprise_url: str,
        channel_hint: str | None | Unset = UNSET,
    ) -> ChannelOut:
        """POST /api/v1/channels — store a new channel; URL is encrypted at rest."""
        body = ChannelCreate(
            name=name, apprise_url=apprise_url, channel_hint=channel_hint,
        ).to_dict()
        return await self._client._typed_request(
            "POST", "/api/v1/channels", model=ChannelOut, json=body, retry_safe=False,
        )

    async def get(self, channel_id: str) -> ChannelOut:
        """GET /api/v1/channels/{id}."""
        return await self._client._typed_request(
            "GET", f"/api/v1/channels/{channel_id}",
            model=ChannelOut, retry_safe=True,
        )

    async def update(
        self, channel_id: str, *,
        name: str | Unset = UNSET,
        apprise_url: str | Unset = UNSET,
        channel_hint: str | None | Unset = UNSET,
    ) -> ChannelOut:
        """PATCH /api/v1/channels/{id} — partial update; only supplied fields are sent."""
        body = ChannelUpdate(
            name=name, apprise_url=apprise_url, channel_hint=channel_hint,
        ).to_dict()
        return await self._client._typed_request(
            "PATCH", f"/api/v1/channels/{channel_id}",
            model=ChannelOut, json=body, retry_safe=False,
        )

    async def delete(self, channel_id: str) -> None:
        """DELETE /api/v1/channels/{id}; 204 on success."""
        response = await self._client._http.request(
            "DELETE", f"/api/v1/channels/{channel_id}",
        )
        if response.status_code >= 400:
            raise error_from_response(response)

    async def test(self, channel_id: str) -> ChannelTestResponse:
        """POST /api/v1/channels/{id}/test — fire a test notification."""
        return await self._client._typed_request(
            "POST", f"/api/v1/channels/{channel_id}/test",
            model=ChannelTestResponse, retry_safe=False,
        )
```

Note on `list()` and `delete()`: the helper handles single-object decoding; lists and 204-no-body responses route through `self._client._http` directly.

Modify `clients/python/src/notifier_client/client.py` — add the import and attach the sub-client:

```python
from notifier_client.sub_clients.channels import ChannelsAPI
```

In `__init__`, after `self._http = httpx.AsyncClient(...)`:

```python
self.channels = ChannelsAPI(self)
```

- [ ] **Step 3.4: Run unit tests to verify they pass**

```bash
cd clients/python && uv run pytest tests/test_channels_api.py -v
```
Expected: PASS (7 tests).

- [ ] **Step 3.5: Write the integration round-trip test**

Create `clients/python/tests/test_channels_integration.py`:

```python
"""Round-trip: channel create → dispatch via that channel → channel delete.

Exercises the typed sub-client surface against a real notifier process. The
channel is a sink:// Apprise URL — no external delivery, just confirms the
plumbing.
"""

import pytest

from notifier_client import NotifierClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_channel_round_trip(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        # 1. Create
        ch = await c.channels.create(
            name="round-trip-test", apprise_url="json://localhost",
        )
        assert ch.id
        assert ch.name == "round-trip-test"

        try:
            # 2. List should include it
            listed = await c.channels.list()
            assert any(x.id == ch.id for x in listed)

            # 3. Dispatch through it
            result = await c.dispatch(
                title_template="t", body_template="b",
                channel_ids=[ch.id], idempotency_key="round-trip-1",
            )
            assert result.id
            assert result.status in {"succeeded", "failed", "partial"}
        finally:
            # 4. Delete
            await c.channels.delete(ch.id)
            remaining = await c.channels.list()
            assert all(x.id != ch.id for x in remaining)
```

- [ ] **Step 3.6: Run the integration test**

```bash
cd clients/python && export $(cat ../../.env 2>/dev/null | xargs) \
  && uv run pytest tests/test_channels_integration.py -m integration -v
```
Expected: PASS (or skip with clear message if `TEST_DATABASE_URL` is unset). If skipped, document and continue — CI will run it.

- [ ] **Step 3.7: Run full SDK suite + lint**

```bash
cd clients/python && uv run pytest && uv run ruff check .
```
Expected: PASS both.

- [ ] **Step 3.8: Commit**

```bash
git add clients/python/src/notifier_client/sub_clients/ \
        clients/python/src/notifier_client/client.py \
        clients/python/tests/test_channels_api.py \
        clients/python/tests/test_channels_integration.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk): add client.channels.* sub-client (typed)

list/create/get/update/delete/test under ChannelsAPI. Returns ChannelOut
and ChannelTestResponse. Integration test round-trips channel create →
dispatch → delete against a live notifier.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 3 acceptance
- `client.channels.{list,create,get,update,delete,test}` all callable, typed-returning.
- 7 unit tests + 1 integration test pass.
- `update()` only sends supplied fields (verified by request-body assertion).

---

## Stage 4: `client.templates.*` sub-client

**Files:**
- Create: `clients/python/src/notifier_client/sub_clients/templates.py`
- Create: `clients/python/tests/test_templates_api.py`
- Modify: `clients/python/src/notifier_client/client.py` (attach `self.templates`)

### Tasks

- [ ] **Step 4.1: Write failing unit tests**

Create `clients/python/tests/test_templates_api.py`. Mirror the channels test layout but exercise:
- `templates.list()` → `list[TemplateOut]`
- `templates.create(name, title_template, body_template, variables_schema=, sample_variables=, tags=)` → `TemplateOut`
- `templates.get(id)` → `TemplateOut`
- `templates.update(id, ...)` → `TemplateOut`
- `templates.delete(id)` → `None`
- `templates.preview(id, variables=...)` → `TemplatePreviewResponse`
- One ValidationError test on `templates.create` (e.g., 422 with `field_path == "body.variables_schema"`).

Sample success body for templates:

```python
_TEMPLATE_BODY = {
    "id": "01HT", "tenant_id": "t1", "name": "alert",
    "title_template": "T", "body_template": "B",
    "variables_schema": None, "sample_variables": None, "tags": None,
    "created_at": "2026-04-30T00:00:00Z",
    "updated_at": "2026-04-30T00:00:00Z",
}
```

Sample preview body:

```python
{"title": "T", "body": "B", "error": None, "error_section": None}
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
cd clients/python && uv run pytest tests/test_templates_api.py -v
```
Expected: FAIL — `client.templates` does not exist.

- [ ] **Step 4.3: Implement `TemplatesAPI`**

Create `clients/python/src/notifier_client/sub_clients/templates.py`. Follow the same shape as `channels.py`. Imports:

```python
from notifier_client.generated.models.template_create import TemplateCreate
from notifier_client.generated.models.template_update import TemplateUpdate
from notifier_client.generated.models.template_preview_request import TemplatePreviewRequest
from notifier_client.generated.types import UNSET, Unset
from notifier_client.types import TemplateOut, TemplatePreviewResponse
```

Method signatures:

```python
async def list(self) -> list[TemplateOut]: ...
async def create(self, *, name: str, title_template: str, body_template: str,
                 variables_schema: dict | None | Unset = UNSET,
                 sample_variables: dict | None | Unset = UNSET,
                 tags: list[str] | None | Unset = UNSET) -> TemplateOut: ...
async def get(self, template_id: str) -> TemplateOut: ...
async def update(self, template_id: str, *, name: str | Unset = UNSET,
                 title_template: str | Unset = UNSET,
                 body_template: str | Unset = UNSET,
                 variables_schema: dict | None | Unset = UNSET,
                 sample_variables: dict | None | Unset = UNSET,
                 tags: list[str] | None | Unset = UNSET) -> TemplateOut: ...
async def delete(self, template_id: str) -> None: ...
async def preview(self, template_id: str, *,
                  variables: dict | None = None) -> TemplatePreviewResponse: ...
```

`preview` uses `TemplatePreviewRequest(variables=variables or UNSET).to_dict()` and routes through `_typed_request` with `retry_safe=False` (POST, no idempotency).

For `variables_schema`/`sample_variables` dict params: pass through to `TemplateCreate` directly — codegen `from_dict` will accept `dict[str, Any]` for the `Type0` variants.

Wire `self.templates = TemplatesAPI(self)` in `NotifierClient.__init__`.

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
cd clients/python && uv run pytest tests/test_templates_api.py -v
```
Expected: PASS.

- [ ] **Step 4.5: Run full suite + lint**

```bash
cd clients/python && uv run pytest && uv run ruff check .
```
Expected: PASS.

- [ ] **Step 4.6: Commit**

```bash
git add clients/python/src/notifier_client/sub_clients/templates.py \
        clients/python/src/notifier_client/client.py \
        clients/python/tests/test_templates_api.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk): add client.templates.* sub-client (typed)

list/create/get/update/delete/preview under TemplatesAPI. Returns
TemplateOut and TemplatePreviewResponse.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 4 acceptance
- `client.templates.{list,create,get,update,delete,preview}` all callable, typed-returning.
- Unit tests cover success + a ValidationError path.

---

## Stage 5: Top-level `client.preview()` (stateless inline render)

**Why a top-level method, not a sub-client:** there is exactly one operation under `/api/v1/preview` (POST). A sub-namespace for a single method is overkill.

**Files:**
- Modify: `clients/python/src/notifier_client/client.py`
- Create: `clients/python/tests/test_preview_api.py`

### Tasks

- [ ] **Step 5.1: Write failing test**

Create `clients/python/tests/test_preview_api.py`:

```python
import httpx
import pytest
import respx

from notifier_client import NotifierClient, PreviewResponse, RetryConfig


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


@respx.mock
@pytest.mark.asyncio
async def test_preview_renders_inline(fast_retry):
    route = respx.post("https://t.local/api/v1/preview").mock(
        return_value=httpx.Response(200, json={
            "title": "hello world", "body": "body world",
            "error": None, "error_section": None,
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.preview(
            title_template="hello {{ who }}",
            body_template="body {{ who }}",
            variables={"who": "world"},
        )
    body = route.calls.last.request.read().decode()
    assert "hello {{ who }}" in body
    assert isinstance(result, PreviewResponse)
    assert result.title == "hello world"


@respx.mock
@pytest.mark.asyncio
async def test_preview_returns_error_section(fast_retry):
    respx.post("https://t.local/api/v1/preview").mock(
        return_value=httpx.Response(200, json={
            "title": None, "body": None,
            "error": "undefined variable", "error_section": "title",
        })
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.preview(
            title_template="{{ missing }}", body_template="b", variables={},
        )
    assert result.error_section == "title"
    assert result.error == "undefined variable"
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
cd clients/python && uv run pytest tests/test_preview_api.py -v
```
Expected: FAIL — `c.preview` does not exist.

- [ ] **Step 5.3: Add `preview()` to `NotifierClient`**

Modify `clients/python/src/notifier_client/client.py`. Add the import:

```python
from notifier_client.types import DispatchOut, PreviewResponse
```

Add the method below `dispatch`:

```python
async def preview(
    self, *,
    title_template: str,
    body_template: str,
    variables: dict[str, Any],
    variables_schema: dict[str, Any] | None = None,
) -> PreviewResponse:
    """POST /api/v1/preview — stateless inline render; never dispatches.

    Returns a PreviewResponse with either ``.title`` + ``.body`` populated
    or ``.error`` + ``.error_section`` set when rendering/validation fails.
    """
    body: dict[str, Any] = {
        "title_template": title_template,
        "body_template": body_template,
        "variables": variables,
    }
    if variables_schema is not None:
        body["variables_schema"] = variables_schema
    return await self._typed_request(
        "POST", "/api/v1/preview",
        model=PreviewResponse, json=body, retry_safe=False,
    )
```

- [ ] **Step 5.4: Run test to verify it passes**

```bash
cd clients/python && uv run pytest tests/test_preview_api.py -v
```
Expected: PASS.

- [ ] **Step 5.5: Full suite + lint**

```bash
cd clients/python && uv run pytest && uv run ruff check .
```

- [ ] **Step 5.6: Commit**

```bash
git add clients/python/src/notifier_client/client.py clients/python/tests/test_preview_api.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk): add top-level client.preview() (typed)

Stateless inline render. Returns PreviewResponse.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 5 acceptance
- `client.preview(...)` returns `PreviewResponse`.
- Both success and error-section paths covered.

---

## Stage 6: `client.apprise.*` sub-client

**Files:**
- Create: `clients/python/src/notifier_client/sub_clients/apprise.py`
- Create: `clients/python/tests/test_apprise_api.py`
- Modify: `clients/python/src/notifier_client/client.py` (attach `self.apprise`)

### Tasks

- [ ] **Step 6.1: Write failing tests**

Create `clients/python/tests/test_apprise_api.py`. Cover:
- `apprise.list_plugins()` → `list[PluginListItem]`
- `apprise.get_plugin("slack")` → `PluginDetail`
- `apprise.assemble("slack", tokens={...}, variant_index=0)` → `AssembleResponse`

Sample bodies:

```python
_LIST_BODY = [
    {"schema": "slack", "service_name": "Slack", "category": "chat",
     "variants": [{"label": "v1"}]}
]
_DETAIL_BODY = {
    "schema": "slack", "service_name": "Slack", "category": "chat",
    "tokens": {}, "variants": [],
}
_ASSEMBLE_BODY = {"url": "slack://hook/AAA/BBB"}
```

(Adjust per the actual generated `PluginListItem`/`PluginDetail`/`AssembleResponse` field sets — read those models when writing the test.)

Add one ValidationError test on `assemble` (422 missing required token).

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
cd clients/python && uv run pytest tests/test_apprise_api.py -v
```
Expected: FAIL — `client.apprise` does not exist.

- [ ] **Step 6.3: Implement `AppriseAPI`**

Create `clients/python/src/notifier_client/sub_clients/apprise.py`:

```python
"""``client.apprise.*`` — plugin catalog + URL assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from notifier_client.errors import error_from_response
from notifier_client.types import AssembleResponse, PluginDetail, PluginListItem

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class AppriseAPI:
    """Plugin catalog under ``/api/v1/apprise``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list_plugins(self) -> list[PluginListItem]:
        """GET /api/v1/apprise/plugins."""
        response = await self._client._http.request(
            "GET", "/api/v1/apprise/plugins",
        )
        if response.status_code >= 400:
            raise error_from_response(response)
        return [PluginListItem.from_dict(item) for item in response.json()]

    async def get_plugin(self, schema: str) -> PluginDetail:
        """GET /api/v1/apprise/plugins/{schema}."""
        return await self._client._typed_request(
            "GET", f"/api/v1/apprise/plugins/{schema}",
            model=PluginDetail, retry_safe=True,
        )

    async def assemble(
        self, schema: str, *, tokens: dict[str, Any], variant_index: int | None = None,
    ) -> AssembleResponse:
        """POST /api/v1/apprise/plugins/{schema}/assemble — build a URL from tokens."""
        body: dict[str, Any] = {"tokens": tokens}
        if variant_index is not None:
            body["variant_index"] = variant_index
        return await self._client._typed_request(
            "POST", f"/api/v1/apprise/plugins/{schema}/assemble",
            model=AssembleResponse, json=body, retry_safe=False,
        )
```

Wire `self.apprise = AppriseAPI(self)` in `NotifierClient.__init__`.

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
cd clients/python && uv run pytest tests/test_apprise_api.py -v
```
Expected: PASS.

- [ ] **Step 6.5: Full suite + lint**

```bash
cd clients/python && uv run pytest && uv run ruff check .
```

- [ ] **Step 6.6: Commit**

```bash
git add clients/python/src/notifier_client/sub_clients/apprise.py \
        clients/python/src/notifier_client/client.py \
        clients/python/tests/test_apprise_api.py
git commit -m "$(cat <<'EOF'
#3 feat(sdk): add client.apprise.* sub-client (typed)

list_plugins/get_plugin/assemble under AppriseAPI. Returns PluginListItem,
PluginDetail, AssembleResponse.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 6 acceptance
- `client.apprise.{list_plugins, get_plugin, assemble}` all callable, typed-returning.
- Unit tests cover success + one ValidationError path.

---

## Stage 7: Documentation, version bump, changelog, ship

**Files:**
- Modify: `clients/python/pyproject.toml`
- Modify: `clients/python/README.md`
- Create: `clients/python/CHANGELOG.md`
- Modify: `clients/python/src/notifier_client/__init__.py` (`__version__ = "0.2.0"`)
- Modify: `AGENTS.md` (mention sub-clients in the SDK row of Project Layout)

### Tasks

- [ ] **Step 7.1: Bump version**

Modify `clients/python/pyproject.toml`:
```toml
version = "0.2.0"
```

Modify `clients/python/src/notifier_client/__init__.py`:
```python
__version__ = "0.2.0"
```

- [ ] **Step 7.2: Write CHANGELOG**

Create `clients/python/CHANGELOG.md`:

```markdown
# Changelog

## 0.2.0 — 2026-05-01

### Breaking
- `dispatch()` now returns `DispatchOut` (typed `attrs` model), not `dict`.

### Added
- `notifier_client.types` — stable public re-exports of generated models.
- `client.channels.{list, create, get, update, delete, test}` returning `ChannelOut` / `ChannelTestResponse`.
- `client.templates.{list, create, get, update, delete, preview}` returning `TemplateOut` / `TemplatePreviewResponse`.
- `client.preview()` — stateless inline render returning `PreviewResponse`.
- `client.apprise.{list_plugins, get_plugin, assemble}` returning `PluginListItem` / `PluginDetail` / `AssembleResponse`.

### Unchanged
- `health()` and `ready()` still return `dict[str, Any]` — server schema is free-form.
- Retry / 429 / idempotency / error semantics identical to 0.1.0.

## 0.1.0 — 2026-04-30

Initial release. `dispatch()`, `health()`, `ready()` only; dict returns; full retry + idempotency + typed errors.
```

- [ ] **Step 7.3: Rewrite README usage section**

Modify `clients/python/README.md`. Replace the `## Usage` block to demonstrate typed returns:

```python
async with NotifierClient(base_url="https://notifier.exe.xyz", api_key="nk_...") as client:
    ch = await client.channels.create(name="ops", apprise_url="slack://...")
    print(ch.id, ch.apprise_url_masked)

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
```

Add a new section `### Sub-clients` listing the three namespaces and their methods.

Add a paragraph noting `health()`/`ready()` still return dict (and why).

- [ ] **Step 7.4: Update AGENTS.md**

Modify `AGENTS.md` — change the `clients/python/` line under Project Layout to mention sub-clients:

> `clients/python/` — `notifier-client` Python SDK; separate `pyproject.toml` + venv (`uv sync` from this dir); `src/notifier_client/generated/` is regenerated from `/openapi.json` via `clients/python/scripts/regen.sh` and must never be hand-edited; CI fails any PR that leaves it stale. Public types in `notifier_client.types`; sub-clients under `client.channels`, `client.templates`, `client.apprise`.

- [ ] **Step 7.5: Run full suite a final time**

```bash
cd clients/python && uv run pytest && uv run ruff check .
```
Expected: PASS.

- [ ] **Step 7.6: Restart the systemd service** (per AGENTS.md "After finishing work")

```bash
sudo systemctl restart notifier
sudo systemctl status notifier --no-pager | head -20
```
Expected: active (running). The server itself didn't change in this work, but restart per project convention so any incidentally regenerated openapi spec is served.

- [ ] **Step 7.7: Commit + push**

```bash
git add clients/python/pyproject.toml \
        clients/python/CHANGELOG.md \
        clients/python/README.md \
        clients/python/src/notifier_client/__init__.py \
        AGENTS.md
git commit -m "$(cat <<'EOF'
#3 docs(sdk)!: bump to 0.2.0 — typed returns + sub-clients

CHANGELOG documents the dispatch() return-type break and new wrapper
namespaces (channels, templates, preview, apprise). README rewritten with
typed examples. AGENTS.md updated to reference sub-clients.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Stage 7 acceptance
- `notifier_client.__version__ == "0.2.0"`.
- `pyproject.toml` version is `0.2.0`.
- `CHANGELOG.md` documents the break.
- README examples all use typed returns.
- Systemd service is active.

---

## Overall Acceptance

- All seven stages committed; `git log --oneline` shows the seven commits in order.
- `cd clients/python && uv run pytest` — full suite green (estimated ~70 unit tests + ~3 integration tests when `TEST_DATABASE_URL` is set).
- `cd clients/python && uv run ruff check .` — clean.
- Public surface: `from notifier_client import (NotifierClient, ChannelOut, TemplateOut, DispatchOut, PreviewResponse, PluginListItem, PluginDetail, AssembleResponse, ChannelTestResponse, TemplatePreviewResponse, AUTO, RetryConfig, AuthError, ValidationError, RateLimited, ServerError, NotifierError, RedactingFilter)` all resolve.
- The four endpoint groups (`channels`, `templates`, `preview`, `apprise`) work end-to-end against a live notifier (validated via the channel-roundtrip integration test; templates/preview/apprise have respx unit coverage and rely on the same `_typed_request` funnel).
- Issue #3 can be closed with the v0.2.0 tag commit.
- No back-compat shims exist anywhere in the package.

## Out of scope (do not do in this plan)
- Pagination wrappers for `list()` methods — server doesn't paginate in v0.
- Pydantic wrappers around the codegen `Unset` sentinels — document the `is not UNSET` idiom in the README and revisit if watcher's adapter friction warrants it.
- Sync facade.
- Other-language clients (`clients/typescript/`, etc.).
- Server-side schema changes — if regen reveals drift, do that in a separate PR before this plan resumes.
- Watcher coordination — explicitly waived; watcher will pick up `v0.2.0` directly when it next pins.

## Risks
- **Codegen rename inside a stage.** If `openapi-python-client` regen happens mid-plan and renames a generated class, `notifier_client.types` re-exports break loudly (Stage 1 surface test catches it). Fix: update the import line in `types.py`; tests pin the stable name.
- **`Unset` ergonomics in `update()` partial PATCH.** The codegen `to_dict` already drops `UNSET` fields; verify in Stage 3 by asserting on the request body that unsupplied fields are absent.
- **`TemplateCreate.from_dict` typing on `variables_schema` / `sample_variables`.** Generated `Type0` variants accept dicts; if pyright/ruff complains in Stage 4, cast at the call site or pass `from_dict` results through. Already verified the codegen handles `dict[str, Any]` inputs cleanly.
