from datetime import UTC, datetime

from src.core.resend.dto import OutgoingEmail
from src.core.resend.exc import ResendRejectedError
from src.core.resend.service import ResendService
from src.worker.exc.letters import LetterExpiredError, LetterRejectedError
from src.worker.letters.dto import Letter
from src.worker.letters.renderer import LetterRenderer


class LettersService:
    def __init__(self, resend: ResendService) -> None:
        self._resend = resend

    async def deliver(self, letter: Letter) -> str:
        """Отправляет письмо через Resend; message_id — ключ идемпотентности у провайдера.

        Returns:
            id письма у провайдера.
        """
        if letter.expires_at <= datetime.now(UTC):
            raise LetterExpiredError({"message_id": letter.message_id})
        rendered = LetterRenderer.render(letter.template, letter.locale, letter.params)
        try:
            return await self._resend.send(
                OutgoingEmail(
                    to=letter.to,
                    subject=rendered.subject,
                    text=rendered.text,
                    html=rendered.html,
                    idempotency_key=letter.message_id,
                )
            )
        except ResendRejectedError as exc:
            raise LetterRejectedError(exc.context) from exc
