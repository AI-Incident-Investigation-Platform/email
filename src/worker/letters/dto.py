from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.worker.letters.enums import LetterTemplate


@dataclass(frozen=True)
class Letter:
    message_id: str
    template: LetterTemplate
    to: str
    locale: str
    params: Mapping[str, str | int]
    expires_at: datetime
    collapse_key: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class RenderedLetter:
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class SeenLetter:
    created_at: datetime
    expires_at: datetime
