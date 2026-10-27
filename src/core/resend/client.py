import httpx

from src.core.resend.exc import ResendTimeoutError, ResendUnavailableError


class ResendClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def post_email(self, payload: dict[str, object], idempotency_key: str) -> httpx.Response:
        try:
            return await self._http.post(
                "/emails", json=payload, headers={"Idempotency-Key": idempotency_key}
            )
        except httpx.TimeoutException as exc:
            raise ResendTimeoutError from exc
        except httpx.HTTPError as exc:
            raise ResendUnavailableError from exc
