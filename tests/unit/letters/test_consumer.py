import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage
from dishka import Provider, Scope, make_async_container, provide

from src.config import cfg
from src.core.rabbitmq.connection import RabbitmqConnection
from src.core.resend.service import ResendService
from src.worker.exc.letters import LetterExpiredError
from src.worker.letters.consumer import ATTEMPT_HEADER, LettersConsumer
from src.worker.letters.dto import Letter
from src.worker.letters.enums import LetterTemplate
from src.worker.letters.service import LettersService
from tests.support.letters import FakeResend, letter_body


@dataclass
class StubMessage:
    """Сообщение брокера: тест видит, чем consumer его закрыл."""

    body: bytes
    headers: dict[str, Any] = field(default_factory=dict)
    message_id: str = "msg-1"
    content_type: str = "application/json"
    acked: bool = False
    rejected: bool = False

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, requeue: bool = False) -> None:
        assert not requeue
        self.rejected = True


@dataclass
class StubExchange:
    published: list[Any] = field(default_factory=list)

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message, routing_key))


@pytest.fixture
async def consumer_for() -> AsyncIterator[Any]:
    containers = []

    def build(resend: FakeResend) -> tuple[LettersConsumer, StubExchange]:
        class TestProvider(Provider):
            letters = provide(LettersService, scope=Scope.REQUEST)

            @provide(scope=Scope.APP)
            def get_resend(self) -> ResendService:
                return resend.service()

        container = make_async_container(TestProvider())
        containers.append(container)
        consumer = LettersConsumer(container, RabbitmqConnection())
        retry = StubExchange()
        consumer._retry_exchange = cast(AbstractExchange, retry)
        return consumer, retry

    yield build
    for container in containers:
        await container.close()


async def handle(consumer: LettersConsumer, message: StubMessage) -> None:
    await consumer.handle(cast(AbstractIncomingMessage, message))


@pytest.mark.case(id="LETTERS-001")
async def test_expired_letter_is_not_sent() -> None:
    resend = FakeResend()
    letter = Letter(
        message_id="m",
        template=LetterTemplate.AUTH_LOGIN_CODE,
        to="user@example.com",
        locale="ru",
        params={"code": "004271", "expires_in": 300},
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(LetterExpiredError):
        await LettersService(resend.service()).deliver(letter)
    assert resend.requests == []


@pytest.mark.case(id="LETTERS-CONSUMER-001")
async def test_outcome_decides_ack_retry_or_dead_letter(consumer_for: Any) -> None:
    sent_consumer, _ = consumer_for(FakeResend(statuses=[200]))
    sent = StubMessage(json.dumps(letter_body()).encode())
    await handle(sent_consumer, sent)

    retry_consumer, retry = consumer_for(FakeResend(statuses=[503]))
    temporary = StubMessage(json.dumps(letter_body()).encode())
    await handle(retry_consumer, temporary)
    exhausted = StubMessage(
        json.dumps(letter_body()).encode(), headers={ATTEMPT_HEADER: cfg.letters.max_attempts}
    )
    await handle(retry_consumer, exhausted)

    rejected_consumer, _ = consumer_for(FakeResend(statuses=[422]))
    rejected = StubMessage(json.dumps(letter_body()).encode())
    await handle(rejected_consumer, rejected)
    malformed = StubMessage(b"{not json")
    await handle(rejected_consumer, malformed)
    expired = StubMessage(
        json.dumps(
            letter_body(expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
        ).encode()
    )
    await handle(rejected_consumer, expired)

    assert sent.acked and not sent.rejected
    assert temporary.acked and not temporary.rejected
    assert len(retry.published) == 1
    retried, routing_key = retry.published[0]
    assert routing_key == cfg.letters.transactional_routing_key
    assert retried.headers[ATTEMPT_HEADER] == 2
    assert retried.body == temporary.body
    assert exhausted.rejected and not exhausted.acked
    assert rejected.rejected and malformed.rejected
    assert expired.acked and not expired.rejected


@pytest.mark.case(id="LETTERS-CONSUMER-002")
async def test_code_never_reaches_logs(consumer_for: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for statuses in ([200], [503], [422]):
        consumer, _ = consumer_for(FakeResend(statuses=statuses))
        await handle(consumer, StubMessage(json.dumps(letter_body()).encode()))

    logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert "004271" not in logged
    assert any(record.message == "Письмо отправлено" for record in caplog.records)
