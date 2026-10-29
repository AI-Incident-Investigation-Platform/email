import httpx

from src.core.resend.exc import ResendTimeoutError, ResendUnavailableError


class ResendClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def post_email(self, payload: dict[str, object], idempotency_key: str) -> httpx.Response:
        return await self._request(
            "POST", "/emails", json=payload, headers={"Idempotency-Key": idempotency_key}
        )

    async def get_usage(self) -> httpx.Response:
        return await self._request("GET", "/usage")

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return await self._http.request(method, path, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise ResendTimeoutError from exc
        except httpx.HTTPError as exc:
            raise ResendUnavailableError from exc
