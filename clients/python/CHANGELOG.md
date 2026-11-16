# Changelog

## 0.4.0 — 2026-11-16

The SDK moves from httpx to [httpx2](https://github.com/pydantic/httpx2), Pydantic's maintained fork of httpx 0.28.1, the version 0.3.x pinned. The fork renamed the package, its logger and `httpcore`, and left the API as it was. Every `NotifierClient` method, argument and return type is unchanged. What a consumer changes is where its own code names httpx (CannObserv/notifier#141).

### Breaking
- **A network failure now raises httpx2's exception, not httpx's.** Once retries are exhausted, the SDK re-raises the transport error as it always has, but `except httpx.HTTPError` or `except httpx.TransportError` around an SDK call no longer matches it. Nothing fails to tell you: the clause just stops catching. Change it to `httpx2.HTTPError` or `httpx2.TransportError`, and declare `httpx2` yourself if your code imports it. A project that imported httpx only to catch these can drop it.
- `NotifierError.response` is an `httpx2.Response`. The attributes are the same.
- The request log line is on the `httpx2` logger, and httpcore's are on `httpcore2.*`. Move any `RedactingFilter`, level or handler you attached to `httpx` or `httpcore`. A filter left on `httpx` sees nothing.
- `notifier_client.retry.RetryTransport` subclasses `httpx2.AsyncBaseTransport` and wraps an httpx2 transport. It isn't exported from the package root.
- The generated client (`notifier_client.generated.Client` and `AuthenticatedClient`, which the package root has never exported) renames `httpx_args` to `httpx2_args`. The same goes for `get_httpx_client`, `set_httpx_client`, `get_async_httpx_client` and `set_async_httpx_client`, which become `*_httpx2_*`. That's openapi-python-client 0.30.0's output.
- **If your tests mock the SDK with respx:** respx mocks httpx only. Call `httpx2.alias_httpx()` before anything imports httpx. respx's own pytest plugin imports httpx at startup, so disable it with `-p no:respx` and load `respx.plugin` from `conftest.py` after the alias. This package's `tests/conftest.py` is a worked example.

### Changed
- The runtime dependency is `httpx2>=2.16.2,<3`, replacing `httpx>=0.28.0,<0.29`. It brings `httpcore2` and `truststore`.
- **TLS verification for an `https://` base URL now uses the operating system's trust store instead of certifi.** On macOS and Windows it goes through `truststore`. On Linux it uses OpenSSL's system CA paths. `SSL_CERT_FILE` and `SSL_CERT_DIR` still take precedence. A certificate chained to a CA that certifi carries but the OS store lacks will stop verifying. Plain `http://` base URLs, including the cohort's calls over the tailnet, are unaffected.
- The `User-Agent` header is `python-httpx2/<version>`.
- `generated/` was regenerated with openapi-python-client 0.30.0. Apart from the httpx2 rename above, the only change is `HealthResponse`'s docstring. It now says a key the server's database doesn't hold gets a 401, and a `development` key it does hold gets a 403 (CannObserv/notifier#138).
- The server runs apprise 2.2.0 (was 1.13.1: 2.1.0 under CannObserv/notifier#111, then 2.2.0 under #174, which carries the fix for GHSA-cfp4-m43r-v9q4). No response schema moved, but three things a consumer can see did:
  - `apprise.list_plugins()` lists 33 more plugin schemas, and `chime` is gone (141 → 173). A `chime://` channel stops delivering and can't be created again. In `get_plugin`, `mailto` loses its `pgpkey` arg and `tgram` gains `album`. For `mailgun`, `mailto`, `slack`, `json`, `syslog` and `tgram`, `assemble`'s `variant_index` still picks the same template.
  - Telegram channels now receive the Markdown source rather than notifier's HTML render. Email channels (`mailto`, `mailgun`) still get the HTML render, and a channel's `?format=` override still wins.
  - A channel that hasn't finished sending after 60 seconds is recorded as a failed attempt, even if apprise finishes delivering it in the background. The realistic case is an unbatched `mailgun` channel with a dozen or more recipients. If you `redeliver` that attempt, those recipients can get the notification twice.

### Removed
- The generated `notifier_client.generated.api.monitors` endpoints and their models (`MonitorCreate`, `MonitorOut`, `MonitorUpdate`, `CheckinRequest`, `CheckinResponse` and their nested types). The server no longer serves `/api/v1/monitors`: dead-man's timers moved to co-status (CannObserv/status), whose check-in contract is unchanged, so consumers switch base URL and key, not code. The public surface never exported these (CannObserv/notifier#83).

### Fixed
- `POST /dispatch` retried with the same `idempotency_key` while the first call is still sending now waits for it and returns 202 with the same dispatch record. Before this fix the retry got a 500 once the first call committed: sequential replay was safe, concurrent replay was not, and a client retries concurrently exactly when the first call timed out. No notification was ever sent twice. If the first call fails and rolls back, the retry delivers as a fresh dispatch (CannObserv/notifier#115).

### Unchanged
- Every `NotifierClient` and sub-client method keeps its signature and return type. Every name in `notifier_client.__all__` and `notifier_client.types` is still there.
- Request paths, bodies and headers are identical to 0.3.2, except `User-Agent` (above). So are retry, `Retry-After`, idempotency and error-mapping semantics. `RetryConfig` takes the same arguments.

## 0.3.2 — 2026-09-30

### Added
- `client.redeliver(dispatch_id)` — retry a dispatch's failed channels, as each one's next attempt under the same dispatch. Until now a transient failure was final: replaying the idempotency key returns the stored `failed` record, and a new key resends to every channel, including those that already succeeded. Channels that succeeded are never resent. Each channel gets at most 5 attempts, and past that the call is a 409. Never auto-retried. `DispatchOut.attempts` can now list a channel more than once; its outcome is the entry with the highest `attempt` (CannObserv/notifier#96).
- `health()` and `ready()` now return `database` and `environment` alongside the existing fields, and the server documents both in `/openapi.json` as `HealthResponse` and `ReadyResponse`. Nothing distinguished notifier's production endpoint from its dev one in-band before this: both serve one working tree, so `build` reports the same SHA on both and will keep doing so. Check `environment` (`"production"` | `"development"` — the same vocabulary an API key is marked with) when pointing a consumer at a notifier, especially a dead-man's timer, where the wrong endpoint inverts the alert rather than merely breaking it (CannObserv/notifier#58).

### Changed
- `/ready`'s 200 and 503 are documented as separate models, `ReadyResponse` and `NotReadyResponse`. The 200's `database` and `environment` are non-nullable — one model covering both statuses would have published them as optional on the path where they are always present. The 503 body is unchanged from every prior release: `{"status": "not_ready", "db": false}`.
- `ready()` raises on a 503 rather than returning the not-ready body, as it always has — now documented, because the server newly models that body and the generated client parses it, so the two layers differ in what a caller can observe. Retry behaviour is unchanged: the 5xx is retried before it is raised.
- `health()` and `ready()` still return `dict[str, Any]`, deliberately, though a typed model now exists for both. These are the first calls made against an endpoint the caller is not yet sure of; a mapping tolerates a field a newer server added.

### Fixed
- Every method that takes an ID or plugin schema (`channels.*`, `templates.*`, `apprise.get_plugin`/`assemble`, `redeliver`) now URL-escapes it as a single path segment, as the generated client always has. Before, the value went into the path unescaped, so `/`, `?`, `#` or `%` changed which URL was requested, and httpx resolved `..`: `redeliver("a/../b?c=1")` requested `/api/v1/dispatch/b?c=1`. The server validates ULIDs, and a key reaches only its own tenant, so the realistic effect was a wrong 404 or hitting a different resource of your own. An ID that is empty, `.` or `..` now raises `ValueError` before any request is sent, because escaping can't stop httpx resolving it: `templates.preview("..")` requested `POST /api/v1/preview`. Valid ULIDs and schema names produce the same URLs as before (CannObserv/notifier#97).
- `POST /dispatch` with a channel listed twice in `channel_ids` sends to it once and returns 202 with one attempt. Before this fix it sent twice, then failed with a 500 whose rollback left no record, so replaying the same idempotency key sent twice more (CannObserv/notifier#96).

## 0.3.1 — 2026-09-01

### Removed
- `python-dateutil` from the SDK's dependencies. openapi-python-client 0.29 parses date fields with `datetime.datetime.fromisoformat` instead of `dateutil.parser.isoparse`, so nothing this package ships imports it any more. A consumer that reached `dateutil` transitively through notifier-client must declare it directly (CannObserv/notifier#45).

### Changed
- **The SDK and the notifier server now carry one version, and this is the release where they meet.** The server's version moves 0.1.0 → 0.3.1; no server 0.2.x ever existed, and the earlier `v0.2.0`/`v0.2.1` tags name SDK versions only. A server you point this client at reports `0.3.1` as `info.version` in `/openapi.json` where it previously reported `0.1.0` — the one consumer-visible effect. Enforced by a gate, not a convention: `tests/ci/test_version_lockstep.py` fails if any version site disagrees, and `tests/ci/test_release_tags.py` fails a release whose tag was never cut — which is why 0.3.0 and 0.3.1 were both released untagged and unreachable until now (CannObserv/notifier#50, closing #49).
- Regenerated `generated/` with openapi-python-client 0.29. Alongside the date parsing above: the status enums derive from `enum.StrEnum` rather than `(str, Enum)`, and the underlying client's context managers and setters return `Self`.

### Unchanged
- **The public API is unaffected.** `str(DispatchOutStatus.SUCCEEDED)`, `f"{...}"` and `== "succeeded"` all behave exactly as they did under `(str, Enum)` on the supported interpreters — checked, not assumed. Wire format, retry, idempotency, and error semantics identical to 0.3.0.

## 0.3.0 — 2026-08-25

### Added
- `AuthErrorDetail` in the generated models. The server now documents `401` and `403` on every `/api/v1` operation, so authentication failures are visible in the OpenAPI spec instead of being undocumented runtime behavior (CannObserv/notifier#22).

### Changed
- Generated operation return types widened from `T | None` to `AuthErrorDetail | T | None`, reflecting the newly documented responses.

### Unchanged
- **The public API is unaffected.** `notifier_client`, `notifier_client.types`, and every sub-client method keep their existing signatures — `channels.list()` still returns `list[ChannelOut]`. The sub-clients issue their own HTTP requests rather than calling `generated/`, so the widening is confined to internals that `clients/python/README.md` already documents as regenerated and not hand-edited.
- Wire format, retry, idempotency, and error semantics identical to 0.2.1.

## 0.2.1 — 2026-05-02

### Added
- `DispatchOutStatus` and `DispatchAttemptOutStatus` enums exported from `notifier_client` and `notifier_client.types`. `DispatchOut.status` and `DispatchAttemptOut.status` are now typed as these enums (previously `str`). String equality is preserved — `result.status == "succeeded"` continues to work.
- `DispatchAttemptOut` exported from `notifier_client` and `notifier_client.types` (was accessible via `DispatchOut.attempts` but not importable directly).

## 0.2.0 — 2026-05-01

### Breaking
- `dispatch()` now returns `DispatchOut` (typed `attrs` model), not `dict`.

### Added
- `notifier_client.types` — stable public re-exports of generated models.
- `client.channels.{list, create, get, update, delete, send_test}` returning `ChannelOut` / `ChannelTestResponse`.
- `client.templates.{list, create, get, update, delete, preview}` returning `TemplateOut` / `TemplatePreviewResponse`.
- `client.preview()` — stateless inline render returning `PreviewResponse`.
- `client.apprise.{list_plugins, get_plugin, assemble}` returning `PluginListItem` / `PluginDetail` / `AssembleResponse`.
- `_typed_request` raises a clean `NotifierError` (not `KeyError`) when a typed endpoint returns 200 with empty body.

### Changed
- `client.channels.test()` renamed to `client.channels.send_test()` for clarity (test is an action, not a verification).
- `dispatch()` now omits `variables` from the request body when caller passes `None` (or omits the kwarg). Previously sent an empty dict; now consistent with how `metadata` is handled.
- Internal: `dispatch()`, `client.preview()`, `apprise.assemble()` now build request bodies via codegen `*Request` models for consistency with the rest of the SDK. Wire format unchanged for documented endpoints.

### Unchanged
- `health()` and `ready()` still return `dict[str, Any]` — server schema is free-form.
- Retry / 429 / idempotency / error semantics identical to 0.1.0.

## 0.1.0 — 2026-04-30

Initial release. `dispatch()`, `health()`, `ready()` only; dict returns; full retry + idempotency + typed errors.
