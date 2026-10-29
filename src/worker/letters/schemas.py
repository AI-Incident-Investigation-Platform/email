from typing import Annotated

from pydantic import AwareDatetime, BaseModel, EmailStr, Field

from src.worker.letters.enums import LetterTemplate


class LetterTask(BaseModel):
    message_id: Annotated[str, Field(min_length=1, max_length=64)]
    template: LetterTemplate
    to: EmailStr
    locale: Annotated[str, Field(pattern=r"^[a-z]{2}$")] = "ru"
    params: dict[str, str | int] = Field(default_factory=dict)
    expires_at: AwareDatetime
    collapse_key: Annotated[str, Field(min_length=1, max_length=320)] | None = None
    created_at: AwareDatetime | None = None
