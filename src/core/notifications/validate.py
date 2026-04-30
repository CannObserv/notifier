"""JSON Schema validation for template variable bags."""

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


@dataclass(frozen=True, slots=True)
class VariablesValidationError(Exception):
    """Raised when ``variables`` fails the template's JSON Schema."""

    message: str
    path: str  # dotted JSON pointer to the offending field; empty for root errors

    def __str__(self) -> str:  # pragma: no cover — trivial
        return f"{self.path or '<root>'}: {self.message}"


def validate_variables(variables: dict[str, Any], schema: dict[str, Any] | None) -> None:
    """Validate ``variables`` against ``schema`` (a JSON Schema document).

    A ``None`` or empty schema is treated as "no validation"; the call is a no-op.
    Raises VariablesValidationError on the first violation, including the JSON
    pointer path so consumers know exactly which field is wrong.
    """
    if not schema:
        return
    try:
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        # Schema itself is malformed — separate from variable-bag problems.
        raise VariablesValidationError(
            message=f"variables_schema is not a valid JSON Schema: {exc.message}",
            path="",
        ) from exc
    errors = sorted(validator.iter_errors(variables), key=lambda e: list(e.path))
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(p) for p in first.absolute_path)
    raise VariablesValidationError(message=first.message, path=path)
