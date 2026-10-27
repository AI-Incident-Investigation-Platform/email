import logging
import time
from datetime import UTC, datetime

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractIncomingMessage
from dishka import AsyncContainer
from opentelemetry import context, propagate, trace
from pydantic import ValidationError

from src.config import cfg
from src.core.errors import (
    AppError,
    ErrorReport,
    IntegrationTimeoutError,
    IntegrationUnavailableError,
)
from src.core.rabbitmq.connection import RabbitmqConnection
from src.worker.exc.letters import LetterExpiredError
from src.worker.letters.dto import Letter
from src.worker.letters.enums import LetterOutcome
from src.worker.letters.metrics import DELIVERY_DURATION, LETTERS
from src.worker.letters.schemas import LetterTask
from src.worker.letters.service import LettersService

log = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"


class LettersConsumer:
    """Принимает задачи из `email.transactional` и решает их судьбу по исходу доставки.

    Временный отказ провайдера — копия задачи в retry-очередь с задержкой и ack
    оригинала, пока не исчерпан лимит попыток; битая задача, отказ провайдера и
    исчерпанные попытки — dead-letter; устаревшая задача — ack без отправки.
    """

    def __init__(self, container: AsyncContainer, connection: RabbitmqConnection) -> None:
        self._container = container
        self._connection = connection
        self._retry_exchange: AbstractExchange | None = None
        self._tracer = trace.get_tracer(__name__)

    async def start(self) -> None:
        connection = await self._connection.connect()
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=cfg.letters.prefetch)
        queue = await self._declare_topology(channel)
        await queue.consume(self.handle)
        log.info("Начат приём задач на письма", extra={"queue": cfg.letters.transactional_queue})

    async def handle(self, message: AbstractIncomingMessage) -> None:
        attempt = int(str((message.headers or {}).get(ATTEMPT_HEADER, 1)))
        parent = propagate.extract({k: str(v) for k, v in (message.headers or {}).items()})
        token = context.attach(parent)
        started = time.perf_counter()
        try:
            with self._tracer.start_as_current_span("letters.deliver"):
                await self._process(message, attempt, started)
        finally:
            context.detach(token)

    async def _process(
        self, message: AbstractIncomingMessage, attempt: int, started: float
    ) -> None:
        try:
            task = LetterTask.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            self._record(
                LetterOutcome.DEAD,
                attempt,
                message.message_id,
                event="Битая задача на письмо отправлена в dead-letter",
            )
            return

        letter = Letter(
            message_id=task.message_id,
            template=task.template,
            to=str(task.to),
            locale=task.locale,
            params=task.params,
            expires_at=task.expires_at,
        )
        try:
            async with self._container() as request:
                service = await request.get(LettersService)
                provider_id = await service.deliver(letter)
        except LetterExpiredError as exc:
            await message.ack()
            self._record(LetterOutcome.EXPIRED, attempt, letter.message_id, letter, exc)
        except (IntegrationUnavailableError, IntegrationTimeoutError) as exc:
            if attempt < cfg.letters.max_attempts:
                await self._retry(message, letter, attempt + 1)
                await message.ack()
                self._record(LetterOutcome.RETRIED, attempt, letter.message_id, letter, exc)
            else:
                await message.reject(requeue=False)
                self._record(LetterOutcome.DEAD, attempt, letter.message_id, letter, exc)
        except Exception as exc:
            await message.reject(requeue=False)
            self._record(LetterOutcome.DEAD, attempt, letter.message_id, letter, exc)
        else:
            await message.ack()
            LETTERS.labels(letter.template.value, LetterOutcome.SENT.value).inc()
            log.info(
                "Письмо отправлено",
                extra={
                    "letter": {
                        "message_id": letter.message_id,
                        "template": letter.template.value,
                        "provider_id": provider_id,
                        "attempt": attempt,
                    }
                },
            )
        finally:
            template = letter.template.value
            DELIVERY_DURATION.labels(template).observe(time.perf_counter() - started)

    async def _retry(self, message: AbstractIncomingMessage, letter: Letter, attempt: int) -> None:
        if self._retry_exchange is None:
            raise RuntimeError("consumer is not started")
        remaining = (letter.expires_at - datetime.now(UTC)).total_seconds()
        await self._retry_exchange.publish(
            aio_pika.Message(
                message.body,
                message_id=message.message_id,
                content_type=message.content_type,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                expiration=max(int(remaining), 1),
                headers={**(message.headers or {}), ATTEMPT_HEADER: attempt},
            ),
            routing_key=cfg.letters.transactional_routing_key,
        )

    @staticmethod
    def _record(
        outcome: LetterOutcome,
        attempt: int,
        message_id: str | None,
        letter: Letter | None = None,
        exc: Exception | None = None,
        event: str | None = None,
    ) -> None:
        template = letter.template.value if letter else "unknown"
        LETTERS.labels(template, outcome.value).inc()
        fields: dict[str, object] = {
            "letter": {
                "message_id": message_id,
                "template": template,
                "attempt": attempt,
                "outcome": outcome.value,
            }
        }
        if exc is not None:
            fields["error"] = ErrorReport.from_exception(exc).to_log()
        level = logging.ERROR if outcome == LetterOutcome.DEAD else logging.WARNING
        log.log(
            level,
            event or LettersConsumer._describe(outcome),
            exc_info=exc if level >= logging.ERROR and not isinstance(exc, AppError) else None,
            extra=fields,
        )

    @staticmethod
    def _describe(outcome: LetterOutcome) -> str:
        match outcome:
            case LetterOutcome.RETRIED:
                return "Провайдер временно не принял письмо, задача отложена на повтор"
            case LetterOutcome.DEAD:
                return "Письмо не отправлено, задача отправлена в dead-letter"
            case LetterOutcome.EXPIRED:
                return "Срок письма истёк, задача отброшена без отправки"
            case LetterOutcome.SENT:
                return "Письмо отправлено"

    async def _declare_topology(self, channel: AbstractChannel) -> aio_pika.abc.AbstractQueue:
        letters = cfg.letters
        exchange = await channel.declare_exchange(
            letters.exchange, aio_pika.ExchangeType.DIRECT, durable=True
        )
        dead_exchange = await channel.declare_exchange(
            letters.dead_exchange, aio_pika.ExchangeType.DIRECT, durable=True
        )
        self._retry_exchange = await channel.declare_exchange(
            letters.retry_exchange, aio_pika.ExchangeType.DIRECT, durable=True
        )
        dead_queue = await channel.declare_queue(
            f"{letters.transactional_queue}.dead",
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-message-ttl": letters.dead_letter_ttl_days * 86_400_000,
            },
        )
        await dead_queue.bind(dead_exchange, routing_key=letters.transactional_routing_key)
        retry_queue = await channel.declare_queue(
            f"{letters.transactional_queue}.retry",
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-message-ttl": letters.retry_delay_seconds * 1000,
                "x-dead-letter-exchange": letters.exchange,
                "x-dead-letter-routing-key": letters.transactional_routing_key,
            },
        )
        await retry_queue.bind(self._retry_exchange, routing_key=letters.transactional_routing_key)
        queue = await channel.declare_queue(
            letters.transactional_queue,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": letters.dead_exchange,
                "x-dead-letter-routing-key": letters.transactional_routing_key,
            },
        )
        await queue.bind(exchange, routing_key=letters.transactional_routing_key)
        return queue
