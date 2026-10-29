import asyncio
import time

import httpx
import pytest

from src.config import cfg
from src.core.resend.client import ResendClient
from src.core.resend.dto import OutgoingEmail
from src.core.resend.exc import (
    ResendQuotaExhaustedError,
    ResendRateLimitedError,
    ResendRejectedError,
    ResendTimeoutError,
    ResendUnavailableError,
)
from src.core.resend.quota import ResendQuota
from src.core.resend.service import ResendService
from tests.support.letters import FakeResend, usage_body

EMAIL = OutgoingEmail(
    to="user@example.com", subject="s", text="t", html="<p>h</p>", idempotency_key="msg-1"
)


@pytest.mark.case(id="RESEND-001")
async def test_email_is_sent_with_idempotency_key_and_sender() -> None:
    resend = FakeResend()

    provider_id = await resend.service().send(EMAIL)

    assert provider_id == "re_1"
    request = resend.requests[0]
    assert request.url.path == "/emails"
    assert request.headers["idempotency-key"] == "msg-1"
    assert resend.payloads()[0] == {
        "from": cfg.resend.from_address,
        "to": ["user@example.com"],
        "subject": "s",
        "text": "t",
        "html": "<p>h</p>",
    }


@pytest.mark.case(id="RESEND-002")
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, ResendRateLimitedError),
        (500, ResendUnavailableError),
        (503, ResendUnavailableError),
        (403, ResendRejectedError),
        (422, ResendRejectedError),
    ],
)
async def test_provider_statuses_map_to_temporary_and_permanent_errors(
    status: int, error: type[Exception]
) -> None:
    with pytest.raises(error):
        await FakeResend(statuses=[status]).service().send(EMAIL)


@pytest.mark.case(id="RESEND-003")
async def test_provider_timeout_is_timeout_error() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    http = httpx.AsyncClient(base_url="https://x", transport=httpx.MockTransport(timeout))

    with pytest.raises(ResendTimeoutError):
        await ResendService(ResendClient(http), ResendQuota()).send(EMAIL)


@pytest.mark.case(id="RESEND-QUOTA-001")
async def test_daily_quota_from_provider_stops_sending_without_request() -> None:
    resend = FakeResend(usage=usage_body(daily_used=99))
    service = resend.service()

    await service.send(EMAIL)
    with pytest.raises(ResendQuotaExhaustedError):
        await service.send(EMAIL)

    assert len(resend.requests) == 1
    assert len(resend.usage_requests) == 1


@pytest.mark.case(id="RESEND-QUOTA-002")
async def test_configured_quota_below_provider_limit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg.resend, "daily_quota", 2)
    resend = FakeResend()
    service = resend.service()

    await service.send(EMAIL)
    await service.send(EMAIL)
    with pytest.raises(ResendQuotaExhaustedError):
        await service.send(EMAIL)

    assert len(resend.requests) == 2


@pytest.mark.case(id="RESEND-QUOTA-003")
@pytest.mark.parametrize("name", ["daily_quota_exceeded", "monthly_quota_exceeded"])
async def test_provider_quota_refusal_stops_further_requests(name: str) -> None:
    resend = FakeResend(statuses=[429], error_name=name)
    service = resend.service()

    with pytest.raises(ResendQuotaExhaustedError):
        await service.send(EMAIL)
    with pytest.raises(ResendQuotaExhaustedError):
        await service.send(EMAIL)

    assert len(resend.requests) == 1


@pytest.mark.case(id="RESEND-QUOTA-004")
async def test_requests_are_spaced_by_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg.resend, "requests_per_second", 20)
    resend = FakeResend()
    service = resend.service()
    started = time.monotonic()

    await asyncio.gather(*(service.send(EMAIL) for _ in range(4)))

    # 4 письма и сверка квот — 5 запросов с интервалом 50 мс
    assert time.monotonic() - started >= 0.2
    assert len(resend.requests) == 4
