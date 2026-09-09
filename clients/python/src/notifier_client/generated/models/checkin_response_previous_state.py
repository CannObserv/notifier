from enum import StrEnum


class CheckinResponsePreviousState(StrEnum):
    MISSING = "missing"
    OK = "ok"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
