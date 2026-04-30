"""Strict Jinja2 rendering for notification templates."""

from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, StrictUndefined
from jinja2 import TemplateError as JinjaTemplateError


class TemplateRenderError(Exception):
    """Raised when a template fails to render (syntax error or undefined ref)."""


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """Result of rendering a (title, body) pair."""

    title: str
    body: str


_env = Environment(
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=False,
)


def render_template(source: str, variables: dict[str, Any]) -> str:
    """Render a single Jinja2 template against ``variables``.

    Uses StrictUndefined so any reference to a missing variable raises a
    TemplateRenderError rather than silently producing an empty string.
    """
    try:
        tpl = _env.from_string(source)
        return tpl.render(**variables)
    except JinjaTemplateError as exc:  # syntax + undefined both subclass this
        raise TemplateRenderError(str(exc)) from exc


def render_pair(
    *, title_template: str, body_template: str, variables: dict[str, Any]
) -> RenderedMessage:
    """Render title + body together; surfaces section-specific errors to callers."""
    title = render_template(title_template, variables)
    body = render_template(body_template, variables)
    return RenderedMessage(title=title, body=body)
