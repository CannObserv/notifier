"""Strict Jinja2 rendering for notification templates."""

from typing import Any

from jinja2 import Environment, StrictUndefined
from jinja2 import TemplateError as JinjaTemplateError


class TemplateRenderError(Exception):
    """Raised when a template fails to render (syntax error or undefined ref)."""


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
