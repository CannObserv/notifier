from enum import StrEnum


class DispatchOutStatus(StrEnum):
    FAILED = "failed"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"

    def __str__(self) -> str:
        return str(self.value)
