"""Shared constants for the notifications package."""

import enum

#: Environment variable holding the branding URL embedded in delivered
#: notifications. Unset means *no link*, which is the default: this was
#: hardcoded to ``https://notifier.exe.xyz``, a hostname that has never had a
#: DNS record — the VM is named ``watcher`` and notifier is a co-located
#: service, not a host. Six Apprise plugins render the value as a clickable
#: link, so the fix is to ship nothing until there is a real address to ship.
APP_URL_ENV_VAR = "NOTIFIER_APP_URL"


class DispatchStatus(enum.StrEnum):
    """Aggregate status of a Dispatch across all channel attempts."""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class DispatchAttemptStatus(enum.StrEnum):
    """Per-channel attempt status."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
