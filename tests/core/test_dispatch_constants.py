"""Verify DispatchStatus / DispatchAttemptStatus string values match the
Pydantic schema Literals and the SDK-generated enums.

If any value is renamed on one side and not the other, this test breaks at
PR time rather than at consumer runtime.
"""

from typing import get_args

from src.api.schemas.dispatch import DispatchAttemptOut, DispatchOut
from src.core.notifications.constants import DispatchAttemptStatus, DispatchStatus


def test_dispatch_status_values():
    assert set(DispatchStatus) == {"succeeded", "partial", "failed"}


def test_dispatch_attempt_status_values():
    assert set(DispatchAttemptStatus) == {"succeeded", "failed"}


def test_dispatch_status_matches_schema_literal():
    schema_values = set(get_args(DispatchOut.model_fields["status"].annotation))
    enum_values = {s.value for s in DispatchStatus}
    assert schema_values == enum_values


def test_dispatch_attempt_status_matches_schema_literal():
    schema_values = set(get_args(DispatchAttemptOut.model_fields["status"].annotation))
    enum_values = {s.value for s in DispatchAttemptStatus}
    assert schema_values == enum_values
