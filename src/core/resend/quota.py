import asyncio
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from src.config import cfg
from src.core.resend.enums import QuotaPeriod
from src.core.resend.exc import ResendQuotaExhaustedError
from src.core.resend.metrics import QUOTA_LIMIT, QUOTA_USED


class ResendQuota:
    """Темп запросов и расход квот писем Resend в пределах пода.

    Истина о расходе — у провайдера: в нём учтены и входящие письма, и отправки мимо
    воркера. Поэтому счёт сверяется с `GET /usage` и с заголовками ответа, а локально
    только резервируется место под письмо до ответа. Пока сверки не было, счёт идёт с нуля
    и до первого отказа 429 провайдера.
    """

    def __init__(self) -> None:
        self._used = dict.fromkeys(QuotaPeriod, 0)
        self._limits = {period: self._configured_limit(period) for period in QuotaPeriod}
        self._resets_at: dict[QuotaPeriod, datetime | None] = dict.fromkeys(QuotaPeriod)
        self._next_request_at = 0.0
        self._refresh_after = 0.0
        self._publish()

    async def wait_turn(self) -> None:
        """Ждёт своей очереди на запрос к провайдеру: запросы идут не чаще `requests_per_second`."""
        now = time.monotonic()
        delay = self._next_request_at - now
        self._next_request_at = max(now, self._next_request_at) + 1 / cfg.resend.requests_per_second
        if delay > 0:
            await asyncio.sleep(delay)

    def claim_refresh(self) -> bool:
        """Решает, сверить ли расход с провайдером сейчас; сверяет один вызов на интервал.

        Returns:
            True, если срок сброса какого-то периода неизвестен или прошёл.
        """
        now = time.monotonic()
        stale = any(resets_at is None for resets_at in self._current_resets().values())
        if not stale or now < self._refresh_after:
            return False
        self._refresh_after = now + cfg.resend.usage_refresh_seconds
        return True

    def apply_usage(
        self, period: QuotaPeriod, used: int, limit: int | None, resets_at: datetime
    ) -> None:
        """Принимает расход периода от провайдера; лимит — меньший из своего и провайдерского."""
        configured = self._configured_limit(period)
        self._limits[period] = configured if limit is None else min(configured, limit)
        self._used[period] = used
        self._resets_at[period] = resets_at
        self._publish()

    def reserve(self) -> None:
        """Занимает место под одно письмо во всех периодах.

        Raises:
            ResendQuotaExhaustedError: квота периода исчерпана до его сброса.
        """
        for period, resets_at in self._current_resets().items():
            if self._used[period] >= self._limits[period]:
                raise ResendQuotaExhaustedError(
                    {
                        "period": period.value,
                        "used": self._used[period],
                        "limit": self._limits[period],
                        "resets_at": resets_at.isoformat() if resets_at else None,
                    }
                )
        for period in QuotaPeriod:
            self._used[period] += 1
        self._publish()

    def release(self) -> None:
        """Возвращает место письма, которое провайдер точно не принял."""
        for period in QuotaPeriod:
            self._used[period] = max(self._used[period] - 1, 0)
        self._publish()

    def observe(self, headers: Mapping[str, str]) -> None:
        """Сверяет счёт с заголовками `x-resend-*-quota` успешного ответа."""
        for period in QuotaPeriod:
            value = headers.get(f"x-resend-{period.value}-quota", "")
            if value.isdigit():
                self._used[period] = max(self._used[period], int(value))
        self._publish()

    def exhaust(self, period: QuotaPeriod) -> None:
        """Отмечает период исчерпанным по отказу провайдера.

        Срок сброса неизвестен — воркер повторит попытку через `usage_refresh_seconds`.
        """
        self._used[period] = self._limits[period]
        if self._resets_at[period] is None:
            self._resets_at[period] = datetime.now(UTC) + timedelta(
                seconds=cfg.resend.usage_refresh_seconds
            )
        self._publish()

    @staticmethod
    def _configured_limit(period: QuotaPeriod) -> int:
        match period:
            case QuotaPeriod.DAILY:
                return cfg.resend.daily_quota
            case QuotaPeriod.MONTHLY:
                return cfg.resend.monthly_quota

    def _current_resets(self) -> dict[QuotaPeriod, datetime | None]:
        """Обнуляет периоды, срок сброса которых прошёл; новый срок узнаётся сверкой."""
        now = datetime.now(UTC)
        for period, resets_at in self._resets_at.items():
            if resets_at is not None and resets_at <= now:
                self._used[period] = 0
                self._resets_at[period] = None
        return dict(self._resets_at)

    def _publish(self) -> None:
        for period in QuotaPeriod:
            QUOTA_USED.labels(period.value).set(self._used[period])
            QUOTA_LIMIT.labels(period.value).set(self._limits[period])
