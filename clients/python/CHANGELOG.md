# Changelog

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
