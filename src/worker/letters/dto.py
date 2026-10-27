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


@dataclass(frozen=True)
class RenderedLetter:
    subject: str
    text: str
    html: str
