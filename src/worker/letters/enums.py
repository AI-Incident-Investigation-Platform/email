from enum import StrEnum


class LetterTemplate(StrEnum):
    AUTH_LOGIN_CODE = "auth.login_code"


class LetterOutcome(StrEnum):
    SENT = "sent"
    RETRIED = "retried"
    DEAD = "dead"
    EXPIRED = "expired"
