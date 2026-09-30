"""Build URL paths from caller-supplied values (#97)."""

from urllib.parse import quote


def segment(value: str) -> str:
    """Escape *value* as exactly one path segment.

    ``safe=""`` escapes ``/`` too, so an ID can never add a segment, a query,
    or a fragment, and ``..`` stays literal instead of being resolved by
    httpx into a different resource. This matches the generated client.
    """
    return quote(str(value), safe="")
