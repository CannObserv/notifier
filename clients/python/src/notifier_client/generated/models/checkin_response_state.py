from enum import StrEnum


class CheckinResponseState(StrEnum):
    MISSING = "missing"
    OK = "ok"
    PENDING = "pending"

    def __str__(self) -> str:
        return str(self.value)
