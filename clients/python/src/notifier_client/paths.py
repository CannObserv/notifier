"""Build URL paths from caller-supplied values (#97)."""

from urllib.parse import quote

#: Values quoting cannot neutralise: dots are unreserved, so ``..`` survives
#: ``quote`` and httpx resolves it, and an empty value leaves an empty segment.
_DOT_SEGMENTS = frozenset({"", ".", ".."})


def segment(value: str) -> str:
    """Escape *value* as exactly one path segment.

    ``safe=""`` escapes ``/`` too, so an ID can never add a segment, a query,
    or a fragment, matching the generated client. A value that is itself a
    dot segment, or empty, is refused with ``ValueError``, since escaping
    cannot stop httpx from resolving it to another endpoint. No ID or plugin
    schema name is either.
    """
    text = str(value)
    if text in _DOT_SEGMENTS:
        raise ValueError(f"{text!r} cannot be a URL path segment")
    return quote(text, safe="")
