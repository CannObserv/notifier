# Color-coded HTML diff output for email channels — Design

**Issue:** [#8](https://github.com/CannObserv/notifier/issues/8)
**Date:** 2026-05-09

## Goal

When dispatching to HTML-native channels (e.g. `mailto://`), render the body with
green/red highlighting on `+`/`-` lines inside ` ```diff ` fenced code blocks,
mirroring GitHub's diff palette. Non-HTML channels (Slack, Discord, plain text)
continue to receive the source Markdown unchanged.

The service stays consumer-agnostic: any consumer can put `diff` fences in a
Markdown body and get colored HTML for HTML targets — Watcher (the first
consumer) is the motivating case but not the only one.

## Approved approach

1. **Full Markdown→HTML pipeline** owned by notifier for HTML targets, using
   **mistune ~= 3.0** with a custom diff-fence renderer. Apprise's translation
   layer is bypassed for HTML-native channels.
2. **Per-channel HTML capability detected at dispatch time** by reading
   `plugin.notify_format` on the resolved Apprise plugin — no scheme heuristics,
   no per-channel hints stored on `Channel`.
3. **`Dispatch.rendered_body` keeps the source Markdown.** HTML rewrite is
   ephemeral, computed inside `dispatch_to_channel` per attempt.

## Data flow

```
render_template (Markdown source)
        │
        ▼
Dispatch.rendered_body  ← persisted (Markdown, channel-agnostic)
        │
        ▼  (per channel, in dispatch_to_channel)
apprise.Apprise().add(url) → plugin.notify_format
        │
        ├── HTML  → markdown_to_email_html(body) → notify(body_format=HTML)
        └── other → notify(body_format=MARKDOWN)   ← unchanged
```

## Key decisions and rationale

### Pipeline scope: full Markdown→HTML, not just diff fences

Mixing Apprise's Markdown-to-HTML translation with our own partial rewrite is
fragile and depends on undocumented behavior of the Markdown library Apprise
ships. Owning the full pipeline for HTML targets is a strictly larger surface
but eliminates the integration ambiguity and produces consistent output.

Tradeoff accepted: bytes on the wire diverge by channel from the same source
body. Mitigated by recording the source Markdown in the dispatch row (see
below), so logs remain channel-agnostic.

### Library: mistune

Pure Python, fast, the simplest renderer-extension API of the three candidates
considered (`mistune`, `markdown-it-py`, `python-markdown`). A custom
diff-fence renderer is a one-class subclass of `mistune.HTMLRenderer`. Single
new dependency, no extras.

### Detection: `plugin.notify_format`

After `apprise.Apprise().add(url)` succeeds, the resolved plugin instance
exposes its native format. Reading it is exact, version-agnostic, and free.
Scheme-string allowlists would drift; per-channel format hints stored on
`Channel` would require a migration plus consumer-visible API surface.

Concrete API: `ap.servers[0].notify_format` — `servers` is a property, not a
method. The dispatcher uses `getattr(..., "notify_format", NotifyFormat.MARKDOWN)`
so a hypothetical future plugin lacking the attribute falls back to Markdown.

### Logging: source Markdown in `Dispatch.rendered_body`

Rejected the alternative of moving "rendered body" to `DispatchAttempt` (per
attempt) because it doubles row storage on multi-channel dispatches and changes
the schema for a presentation concern. Also rejected adding a
`rendered_body_html` companion field on `Dispatch` (schema bloat for v0). HTML
output is reproducible from the Markdown + the dispatch logic, so we don't
need to store it.

### Inline styles, no classes

Email clients strip `<style>` blocks and ignore class selectors. All styling
inline. `display:block` on each `<span>` so backgrounds extend the full width
of the `<pre>` even in Gmail. `white-space:pre` preserves diff alignment.
Palette borrowed from GitHub.

```html
<pre style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;
  line-height:1.45;background:#f6f8fa;padding:12px;border-radius:6px;
  overflow-x:auto;white-space:pre">
  <span style="display:block;background:#e6ffec;color:#1a7f37"> + added</span>
  <span style="display:block;background:#ffebe9;color:#cf222e"> - removed</span>
  <span style="display:block;color:#57606a">  @@ hunk header @@</span>
  <span style="display:block">  context</span>
</pre>
```

## Module layout

### Created

- `src/core/notifications/html_render.py` — pure functions, no Apprise import:
  - `markdown_to_email_html(body: str) -> str` — top-level entry; mistune
    renderer with diff-fence extension; returns HTML suitable for
    `body_format=HTML`.
  - `_render_diff_block(code: str) -> str` — internal; takes raw fence body,
    returns `<pre>…</pre>` with one `<span>` per line, HTML-escaped, classified
    by leading char.
  - `_classify_diff_line(line: str) -> Literal["add","del","meta","ctx"]` —
    `+` → add, `-` → del, `@@`/`+++`/`---` → meta, else ctx.
- `tests/core/notifications/test_html_render.py` — unit tests for the above.

### Modified

- `src/core/notifications/dispatcher.py` — after `ap.add(url)` succeeds, read
  `ap.servers()[0].notify_format`; branch on `NotifyFormat.HTML`. The
  `body_format=NotifyFormat.MARKDOWN` literal becomes a variable.
- `tests/core/notifications/test_dispatcher.py` (or new file) — extend.
- `pyproject.toml` — add `mistune ~= 3.0`.

### Untouched

- DB schema — no migration.
- API schemas / OpenAPI — no consumer-visible surface change.
- Channel model — no per-channel format hint.
- Watcher — continues to emit Markdown unchanged.

## Test plan

### Unit (no Apprise)

- `markdown_to_email_html`:
  - Diff fence with `+`/`-`/`@@`/context lines → expected `<pre>` + colored
    `<span>`s with HTML-escaped content.
  - Non-diff fenced blocks (` ```python `, plain ` ``` `) render as standard
    `<pre><code>` with no diff styling.
  - XSS payload `<script>alert(1)</script>` inside a diff line → escaped, no
    raw tags emitted.
  - Multiple diff fences in one body — each independently styled.
  - Headers, bold, lists outside a diff fence still render correctly.
- `_classify_diff_line` — table-driven over each prefix.

### Integration

- Dispatch with a `mailto://` channel → captured Apprise call uses
  `body_format=HTML` and body contains the colored spans.
- Dispatch with a `slack://` channel → `body_format=MARKDOWN` and body equals
  the unmodified Markdown source.
- `Dispatch.rendered_body` row equals the Markdown source in both cases.

### Manual

- Smoke against Gmail (web) and Apple Mail before closing the issue. Document
  the result in the closing comment.

## Risk register

- **mistune output stability across versions** — pin major version in
  `pyproject.toml`; tests assert specific HTML strings, which catch breakage
  on upgrade.
- **Plugin attribute access** — `plugin.notify_format` is documented Apprise
  API; defensively `hasattr`-check and fall back to `MARKDOWN` if missing.
- **Email client rendering variance** — manual smoke test (above) before
  shipping.

## Out of scope

- No `body_format` field on `DispatchRequest`. Auto-detection from the channel
  is sufficient; revisit when a real consumer asks for an override.
- No per-channel format hint stored on `Channel`. Detection from the plugin is
  exact and free.
- No Markdown extensions beyond CommonMark + diff-fence styling. Tables,
  footnotes, etc. are future work behind a separate decision.
- No specific testing of HTML for non-`mailto://` HTML-native plugins (some
  webhooks qualify but are rare in practice). Detection is generic so they
  will work; we just don't add coverage now.
