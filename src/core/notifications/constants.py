"""Shared constants for the notifications package."""

import enum

APP_URL = "https://notifier.exe.xyz"


class DispatchStatus(enum.StrEnum):
    """Aggregate status of a Dispatch across all channel attempts."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class DispatchAttemptStatus(enum.StrEnum):
    """Per-channel attempt status."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
