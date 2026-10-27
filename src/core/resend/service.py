from http import HTTPStatus

import httpx

from src.config import cfg
from src.core.resend.client import ResendClient
from src.core.resend.dto import OutgoingEmail
from src.core.resend.exc import ResendRejectedError, ResendUnavailableError


class ResendService:
    def __init__(self, client: ResendClient) -> None:
        self._client = client

    async def send(self, email: OutgoingEmail) -> str:
        """Отправляет письмо; повтор с тем же idempotency_key Resend не дублирует.

        Returns:
            id письма у провайдера.

        Raises:
            ResendUnavailableError: 429 или 5xx — можно повторить позже.
            ResendTimeoutError: провайдер не ответил.
            ResendRejectedError: 4xx — повтор не поможет.
        """
        response = await self._client.post_email(
            {
                "from": cfg.resend.from_address,
                "to": [email.to],
                "subject": email.subject,
                "text": email.text,
                "html": email.html,
            },
            email.idempotency_key,
        )
        status = response.status_code
        if status == HTTPStatus.TOO_MANY_REQUESTS or status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise ResendUnavailableError({"status": status})
        body = self._json(response)
        if status >= HTTPStatus.BAD_REQUEST:
            raise ResendRejectedError({"status": status, "name": body.get("name")})
        provider_id = body.get("id")
        if not isinstance(provider_id, str):
            raise ResendUnavailableError({"status": status, "reason": "no_id"})
        return provider_id

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, object]:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}
