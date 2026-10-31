from enum import StrEnum


class LetterTemplate(StrEnum):
    AUTH_LOGIN_CODE = "auth.login_code"
    AUTH_REGISTER_CODE = "auth.register_code"
    AUTH_EMAIL_CHANGE_CURRENT_CODE = "auth.email_change_current_code"
    AUTH_EMAIL_CHANGE_NEW_CODE = "auth.email_change_new_code"
    AUTH_EMAIL_CHANGED = "auth.email_changed"
    PROJECTS_INVITATION = "projects.invitation"


class LetterOutcome(StrEnum):
    SENT = "sent"
    RETRIED = "retried"
    DEAD = "dead"
    EXPIRED = "expired"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"
