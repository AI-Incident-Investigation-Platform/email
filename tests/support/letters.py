import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.core.resend.client import ResendClient
from src.core.resend.service import ResendService


def letter_body(**overrides: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "message_id": "0196f2c4-6f0e-7a51-9c3e-1d2b3a4c5d6e",
        "template": "auth.login_code",
        "to": "user@example.com",
        "locale": "ru",
        "params": {"code": "004271", "expires_in": 300},
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    body.update(overrides)
    return body


@dataclass
class FakeResend:
    """Подменяет HTTP-транспорт к Resend: отвечает по очереди заданными статусами."""

    statuses: list[int] = field(default_factory=lambda: [200])
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        def respond(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            if status == 200:
                return httpx.Response(200, json={"id": f"re_{len(self.requests)}"})
            return httpx.Response(status, json={"name": "test_error", "message": "x"})

        return respond

    def payloads(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]

    def service(self) -> ResendService:
        http = httpx.AsyncClient(
            base_url="https://api.resend.test", transport=httpx.MockTransport(self.handler())
        )
        return ResendService(ResendClient(http))
