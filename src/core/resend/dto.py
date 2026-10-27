from dataclasses import dataclass


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str
    idempotency_key: str
