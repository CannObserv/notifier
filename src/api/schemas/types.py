"""Shared Pydantic field types for API boundary validation."""

from typing import Annotated, Any

from pydantic import AfterValidator, GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from ulid import ULID
from ulid import base32 as _ulid_base32

from src.core.notifications.validate import VariablesValidationError, check_schema_document

# Derived from ulid.base32.ENCODE — the library's canonical Crockford alphabet.
# Letters included in both cases: the runtime normalises lowercase → uppercase before
# parsing, so the OpenAPI pattern and the runtime validator accept the same input space.
_ULID_ALPHA = "".join(c for c in _ulid_base32.ENCODE if c.isalpha())
_ULID_PATTERN = f"^[{_ulid_base32.ENCODE}{_ULID_ALPHA.lower()}]{{26}}$"


class ULIDStr(str):
    """26-char Crockford base32 ULID string, normalised to uppercase.

    Use on all ID fields that cross the API boundary (path params, request
    body ``*_id`` fields). Invalid values produce a 422 with the field path
    rather than a silent 404.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string", "pattern": _ULID_PATTERN}

    @classmethod
    def _validate(cls, value: Any) -> "ULIDStr":
        s = str(value).upper()
        try:
            ULID.from_str(s)
        except ValueError:
            raise ValueError(f"invalid ULID: {value!r}")
        return cls(s)


def _check_json_schema(value: dict[str, Any]) -> dict[str, Any]:
    """Reject a malformed JSON Schema at the API boundary.

    Never called with ``None``: on ``JSONSchemaDict | None`` the union matches
    a null against NoneType and this validator is not reached.
    """
    try:
        check_schema_document(value)
    except VariablesValidationError as exc:
        # Pydantic surfaces ValueError as a 422 entry with this field's `loc`.
        raise ValueError(exc.message) from exc
    return value


JSONSchemaDict = Annotated[dict[str, Any], AfterValidator(_check_json_schema)]
"""A JSON Schema document, checked against the 2020-12 metaschema on write.

Stored schemas used to be opaque dicts: a broken one was accepted with a 201
and only refused at dispatch time, once per dispatch, on the request that
mattered (#28). Validating here rather than in the route bodies covers POST and
PATCH from one definition, names the field in `loc`, and emits no OpenAPI diff —
FastAPI already declares 422/HTTPValidationError on both routes, so the
generated client needs no regeneration.

Not used by the preview endpoints: POST /preview answers 200 with
`{error, error_section}` by design, and a hard 422 would break that contract.
"""
