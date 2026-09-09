from enum import StrEnum


class CheckinRequestStatus(StrEnum):
    ALERT = "alert"
    OK = "ok"

    def __str__(self) -> str:
        return str(self.value)
