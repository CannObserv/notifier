"""Markdown→HTML rendering for HTML-native notification channels.

The dispatcher invokes :func:`markdown_to_email_html` when the resolved Apprise
plugin advertises ``NotifyFormat.HTML`` (e.g. ``mailto://``). The output is
suitable for ``Apprise.notify(body_format=NotifyFormat.HTML)``.

The single value-add over a plain Markdown renderer is colored styling for
``+``/``-`` lines inside ```` ```diff ```` fenced blocks, mirroring GitHub's
diff palette. Everything else is standard CommonMark via mistune.

All styles are inline; email clients strip ``<style>`` blocks and ignore class
selectors. ``display:block`` on each line ``<span>`` ensures the background
extends the full width of the ``<pre>`` even in Gmail.
"""

from html import escape
from typing import Literal

import mistune

DiffLineKind = Literal["add", "del", "meta", "ctx"]

_PRE_STYLE = (
    "font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;"
    "line-height:1.45;background:#f6f8fa;padding:12px;border-radius:6px;"
    "overflow-x:auto;white-space:pre"
)
_LINE_STYLES: dict[DiffLineKind, str] = {
    "add": "display:block;background:#e6ffec;color:#1a7f37",
    "del": "display:block;background:#ffebe9;color:#cf222e",
    "meta": "display:block;color:#57606a",
    "ctx": "display:block",
}


def _classify_diff_line(line: str) -> DiffLineKind:
    """Classify a single diff line by its leading marker.

    File markers (``+++``/``---``) and hunk headers (``@@``) are ``meta``;
    plain ``+`` and ``-`` lines are ``add``/``del``; everything else is
    context.
    """
    if line.startswith(("+++", "---", "@@")):
        return "meta"
    if line.startswith("+"):
        return "add"
    if line.startswith("-"):
        return "del"
    return "ctx"


def _render_diff_block(code: str) -> str:
    """Render a diff fence body as a styled ``<pre>`` with one span per line."""
    lines = code.splitlines()
    spans = [
        f'<span style="{_LINE_STYLES[_classify_diff_line(line)]}">{escape(line)}</span>'
        for line in lines
    ]
    return f'<pre style="{_PRE_STYLE}">{"".join(spans)}</pre>\n'


class _DiffAwareRenderer(mistune.HTMLRenderer):
    """HTML renderer that swaps ```diff fenced blocks for styled output."""

    def block_code(self, code: str, info: str | None = None) -> str:
        if info and info.strip().split(None, 1)[0].lower() == "diff":
            return _render_diff_block(code)
        return super().block_code(code, info)


# mistune.Markdown is safe to share across calls — no per-call mutable state on
# the parser/renderer for this configuration.
_render_markdown = mistune.create_markdown(renderer=_DiffAwareRenderer(escape=True))


def markdown_to_email_html(body: str) -> str:
    """Render a Markdown body to HTML with colored diff fences.

    Suitable for dispatching with ``Apprise.notify(body_format=NotifyFormat.HTML)``
    on plugins whose ``notify_format`` is ``HTML`` (e.g. ``mailto://``).
    """
    return _render_markdown(body)
