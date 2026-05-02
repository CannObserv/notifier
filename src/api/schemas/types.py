"""Shared Pydantic field types for API boundary validation."""

from typing import Any

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, core_schema
from ulid import ULID
from ulid import base32 as _ulid_base32

# Derived from ulid.base32.ENCODE — the library's canonical Crockford alphabet.
# Keeping this in sync with the runtime validator (ULID.from_str) is intentional:
# both point at the same source of truth so they cannot diverge.
_ULID_PATTERN = f"^[{_ulid_base32.ENCODE}]{{26}}$"


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
