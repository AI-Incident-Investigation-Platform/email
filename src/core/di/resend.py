from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide

from src.config import cfg
from src.core.resend.client import ResendClient
from src.core.resend.quota import ResendQuota
from src.core.resend.service import ResendService


class ResendProvider(Provider):
    resend_client = provide(ResendClient, scope=Scope.APP)
    resend_quota = provide(ResendQuota, scope=Scope.APP)
    resend_service = provide(ResendService, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_http(self) -> AsyncIterator[httpx.AsyncClient]:
        http = httpx.AsyncClient(
            base_url=cfg.resend.base_url,
            timeout=cfg.resend.timeout_seconds,
            headers={"Authorization": f"Bearer {cfg.resend.api_key}"},
        )
        yield http
        await http.aclose()
