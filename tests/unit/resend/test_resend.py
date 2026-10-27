import httpx
import pytest

from src.config import cfg
from src.core.resend.client import ResendClient
from src.core.resend.dto import OutgoingEmail
from src.core.resend.exc import ResendRejectedError, ResendTimeoutError, ResendUnavailableError
from src.core.resend.service import ResendService
from tests.support.letters import FakeResend

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
        (429, ResendUnavailableError),
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
        await ResendService(ResendClient(http)).send(EMAIL)
