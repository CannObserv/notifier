# Changelog

## Unreleased

### Added
- `client.monitors.*` — CRUD for notifier's dead-man's timers plus `checkin()`, the method a consumer calls on every tick of its own probe. Notifier alerts on the *absence* of a check-in, so a probe that only speaks up when it finds something is silent in exactly the cases that matter: a stopped timer, a wedged process, a dead node (CannObserv/notifier#56).
- `MonitorOut`, `MonitorOutState`, `CheckinResponse`, and `CheckinResponseState` exported from `notifier_client` and `notifier_client.types`.
- `checkin()` is auto-retried on transport and 5xx failures, alone among the write methods. A dropped heartbeat is indistinguishable from a dead consumer, and the replay is harmless: the second check-in simply overwrites the first.
- `health()` and `ready()` now return `database` and `environment` alongside the existing fields, and the server documents both in `/openapi.json` as `HealthResponse` and `ReadyResponse`. Nothing distinguished notifier's production endpoint from its dev one in-band before this: both serve one working tree, so `build` reports the same SHA on both and will keep doing so. Check `environment` (`"production"` | `"development"` — the same vocabulary an API key is marked with) when pointing a consumer at a notifier, especially a dead-man's timer, where the wrong endpoint inverts the alert rather than merely breaking it (CannObserv/notifier#58).

### Changed
- `/ready`'s 200 and 503 are documented as separate models, `ReadyResponse` and `NotReadyResponse`. The 200's `database` and `environment` are non-nullable — one model covering both statuses would have published them as optional on the path where they are always present. The 503 body is unchanged from every prior release: `{"status": "not_ready", "db": false}`.
- `health()` and `ready()` still return `dict[str, Any]`, deliberately, though a typed model now exists for both. These are the first calls made against an endpoint the caller is not yet sure of; a mapping tolerates a field a newer server added.

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
