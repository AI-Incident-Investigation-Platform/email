import logging
from http import HTTPStatus

import httpx
from pydantic import ValidationError

from src.config import cfg
from src.core.errors import ErrorReport
from src.core.resend.client import ResendClient
from src.core.resend.dto import OutgoingEmail
from src.core.resend.enums import QuotaPeriod
from src.core.resend.exc import (
    ResendQuotaExhaustedError,
    ResendRateLimitedError,
    ResendRejectedError,
    ResendTimeoutError,
    ResendUnavailableError,
)
from src.core.resend.quota import ResendQuota
from src.core.resend.schemas import UsageResponse

log = logging.getLogger(__name__)


class ResendService:
    def __init__(self, client: ResendClient, quota: ResendQuota) -> None:
        self._client = client
        self._quota = quota

    async def send(self, email: OutgoingEmail) -> str:
        """Отправляет письмо в пределах квот; повтор с тем же idempotency_key Resend не дублирует.

        Returns:
            id письма у провайдера.

        Raises:
            ResendQuotaExhaustedError: суточная или месячная квота исчерпана — ждать сброса.
            ResendRateLimitedError: провайдер ограничил частоту — повторить чуть позже.
            ResendUnavailableError: 5xx или сеть — можно повторить позже.
            ResendTimeoutError: провайдер не ответил; письмо могло уйти.
            ResendRejectedError: 4xx — повтор не поможет.
        """
        await self._refresh_usage()
        self._quota.reserve()
        await self._quota.wait_turn()
        try:
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
        except ResendUnavailableError:
            self._quota.release()
            raise
        status = response.status_code
        body = self._json(response)
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            raise self._limited(body.get("name"))
        if status >= HTTPStatus.BAD_REQUEST:
            self._quota.release()
            if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
                raise ResendUnavailableError({"status": status})
            raise ResendRejectedError({"status": status, "name": body.get("name")})
        self._quota.observe(response.headers)
        provider_id = body.get("id")
        if not isinstance(provider_id, str):
            raise ResendUnavailableError({"status": status, "reason": "no_id"})
        return provider_id

    def _limited(self, name: object) -> ResendQuotaExhaustedError | ResendRateLimitedError:
        match name:
            case "daily_quota_exceeded":
                period = QuotaPeriod.DAILY
            case "monthly_quota_exceeded":
                period = QuotaPeriod.MONTHLY
            case _:
                self._quota.release()
                return ResendRateLimitedError({"name": name})
        self._quota.exhaust(period)
        return ResendQuotaExhaustedError({"period": period.value})

    async def _refresh_usage(self) -> None:
        """Сверяет расход квот с провайдером; сбой сверки не мешает отправке."""
        if not self._quota.claim_refresh():
            return
        await self._quota.wait_turn()
        try:
            response = await self._client.get_usage()
        except (ResendUnavailableError, ResendTimeoutError) as exc:
            log.warning(
                "Не удалось сверить расход квот с провайдером",
                extra={"error": ErrorReport.from_exception(exc).to_log()},
            )
            return
        if response.status_code != HTTPStatus.OK:
            log.warning(
                "Провайдер не отдал расход квот",
                extra={"resend": {"status": response.status_code}},
            )
            return
        try:
            usage = UsageResponse.model_validate_json(response.content).emails
        except ValidationError:
            log.warning("Провайдер вернул расход квот в неизвестном формате")
            return
        if usage.daily is not None:
            daily = usage.daily
            self._quota.apply_usage(QuotaPeriod.DAILY, daily.used, daily.limit, daily.resets_at)
        monthly = usage.monthly
        self._quota.apply_usage(QuotaPeriod.MONTHLY, monthly.used, monthly.limit, monthly.resets_at)

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, object]:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}
