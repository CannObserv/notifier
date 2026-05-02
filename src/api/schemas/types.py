"""Shared Pydantic field types for API boundary validation."""

from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from ulid import ULID

# Crockford base32 alphabet used by ULID (no I, L, O, U)
_ULID_PATTERN = "^[0-9A-HJKMNP-TV-Z]{26}$"


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
        except Exception:
            raise ValueError(f"invalid ULID: {value!r}")
        return cls(s)
