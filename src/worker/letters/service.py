from datetime import UTC, datetime

from src.core.resend.dto import OutgoingEmail
from src.core.resend.exc import (
    ResendQuotaExhaustedError,
    ResendRateLimitedError,
    ResendRejectedError,
)
from src.core.resend.service import ResendService
from src.worker.exc.letters import (
    LetterDeferredError,
    LetterExpiredError,
    LetterRejectedError,
    LetterSupersededError,
)
from src.worker.letters.dto import Letter
from src.worker.letters.latest import LatestLetters
from src.worker.letters.renderer import LetterRenderer


class LettersService:
    def __init__(self, resend: ResendService, latest: LatestLetters) -> None:
        self._resend = resend
        self._latest = latest

    async def deliver(self, letter: Letter) -> str:
        """Отправляет письмо через Resend; message_id — ключ идемпотентности у провайдера.

        Returns:
            id письма у провайдера.

        Raises:
            LetterExpiredError: срок письма истёк.
            LetterSupersededError: есть более новое письмо с тем же ключом вытеснения.
            LetterDeferredError: квота или частота провайдера — письмо ждёт.
            LetterRejectedError: провайдер отклонил письмо.
        """
        if letter.expires_at <= datetime.now(UTC):
            raise LetterExpiredError({"message_id": letter.message_id})
        if self._latest.is_superseded(letter):
            raise LetterSupersededError({"message_id": letter.message_id})
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
        except (ResendQuotaExhaustedError, ResendRateLimitedError) as exc:
            raise LetterDeferredError(exc.context) from exc
        except ResendRejectedError as exc:
            raise LetterRejectedError(exc.context) from exc
