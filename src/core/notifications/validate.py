"""JSON Schema validation for template variable bags."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

# Keywords whose values are instance data, not subschemas. A `$ref` key inside
# one is a payload the consumer wants matched literally, not a reference to
# resolve — descending into them would reject a perfectly valid schema.
_DATA_KEYWORDS = frozenset({"const", "enum", "default", "examples"})


@dataclass(frozen=True, slots=True)
class VariablesValidationError(Exception):
    """Raised when ``variables`` fails the template's JSON Schema."""

    message: str
    path: str  # dotted JSON pointer to the offending field; empty for root errors

    def __str__(self) -> str:  # pragma: no cover — trivial
        return f"{self.path or '<root>'}: {self.message}"


class SchemaDocumentError(VariablesValidationError):
    """Raised when the *schema* is at fault, rather than the variable bag.

    A subclass so every existing ``except VariablesValidationError`` keeps
    working; routes that want to name the offending input separately catch
    this first and report ``variables_schema`` instead of ``variables``.
    """


def _iter_schema_refs(node: Any) -> Iterator[str]:
    """Yield every ``$ref`` string in ``node``, skipping instance-data keywords."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for keyword, value in node.items():
            if keyword not in _DATA_KEYWORDS:
                yield from _iter_schema_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_schema_refs(item)


def _pointer_resolves(document: dict[str, Any], pointer: str) -> bool:
    """Walk an RFC 6901 JSON pointer (already stripped of its leading ``#``)."""
    node: Any = document
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return False
            node = node[int(token)]
        elif isinstance(node, dict) and token in node:
            node = node[token]
        else:
            return False
    return True


def _check_schema_refs(schema: dict[str, Any]) -> None:
    """Reject references this service will never be able to resolve.

    ``check_schema`` only checks *shape*: ``{"$ref": "https://example.com/s"}``
    is a metaschema-valid document, so it stored cleanly and then raised
    ``Unresolvable`` out of ``iter_errors`` on the first dispatch — an
    exception that is not a SchemaError and that no route catches. Templates
    carry self-contained variable bags, so nothing legitimate needs an external
    reference, and refusing one on write beats discovering it at dispatch.

    Local pointers are resolved here so a dangling ``#/$defs/missing`` is
    caught too. A plain ``#anchor`` cannot be resolved this cheaply and is
    accepted; the dispatch-time guard turns that into a 422, not a 500.
    """
    for ref in _iter_schema_refs(schema):
        if not ref.startswith("#"):
            raise SchemaDocumentError(
                message=(
                    f"variables_schema is not a valid JSON Schema: $ref {ref!r} is external; "
                    "only references within the document are supported"
                ),
                path="",
            )
        if ref.startswith("#/") and not _pointer_resolves(schema, ref[1:]):
            raise SchemaDocumentError(
                message=(
                    f"variables_schema is not a valid JSON Schema: $ref {ref!r} "
                    "resolves to nothing in this document"
                ),
                path="",
            )


def check_schema_document(schema: dict[str, Any] | None) -> None:
    """Check that ``schema`` is a well-formed JSON Schema document.

    A ``None`` or empty schema means "no validation" and passes: ``{}`` is a
    valid schema that constrains nothing, and ``check_schema(None)`` would
    otherwise reject the request that clears a template's schema.

    check_schema, not the constructor: ``Draft202012Validator(schema)`` accepts
    anything and defers the complaint to validation time, where it surfaces as
    UnknownType — an exception no caller here raises or catches. The API
    boundary calls this on write (#28) so a broken schema is refused by the
    request that introduced it; validate_variables calls it again at dispatch
    time, which is what covers templates stored before that landed.
    """
    if not schema:
        return
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        # Schema itself is malformed — separate from variable-bag problems.
        raise SchemaDocumentError(
            message=f"variables_schema is not a valid JSON Schema: {exc.message}",
            path="",
        ) from exc
    _check_schema_refs(schema)


def validate_variables(variables: dict[str, Any], schema: dict[str, Any] | None) -> None:
    """Validate ``variables`` against ``schema`` (a JSON Schema document).

    A ``None`` or empty schema is treated as "no validation"; the call is a no-op.
    Raises VariablesValidationError on the first violation, including the JSON
    pointer path so consumers know exactly which field is wrong.
    """
    if not schema:
        return
    check_schema_document(schema)
    validator = Draft202012Validator(schema)
    try:
        errors = sorted(validator.iter_errors(variables), key=lambda e: list(e.path))
    except Unresolvable as exc:
        # Resolution happens lazily, per instance, so a reference the write-time
        # guard never got to judge (a `#anchor`, or a row stored before that
        # guard landed) surfaces here. Uncaught it leaves the route as a 500.
        raise SchemaDocumentError(
            message=f"variables_schema is not a valid JSON Schema: {exc}",
            path="",
        ) from exc
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(p) for p in first.absolute_path)
    raise VariablesValidationError(message=first.message, path=path)
