from enum import Enum


class DispatchOutStatus(str, Enum):
    FAILED = "failed"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"

    def __str__(self) -> str:
        return str(self.value)
