import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel
from dishka import Provider, Scope, make_async_container, provide

from src.config import cfg
from src.core.di import RabbitmqProvider
from src.core.rabbitmq.connection import RabbitmqConnection
from src.core.resend.service import ResendService
from src.worker.letters.consumer import LettersConsumer
from src.worker.letters.latest import LatestLetters
from src.worker.letters.service import LettersService
from tests.support.letters import FakeResend, letter_body


@pytest.fixture
async def channel() -> AsyncIterator[AbstractChannel]:
    connection = await aio_pika.connect(cfg.rabbitmq.url)
    yield await connection.channel()
    await connection.close()


@pytest.fixture
async def start_worker() -> AsyncIterator[Callable[[FakeResend], Awaitable[None]]]:
    containers = []

    async def start(resend: FakeResend) -> None:
        class TestResendProvider(Provider):
            letters = provide(LettersService, scope=Scope.REQUEST)
            latest = provide(LatestLetters, scope=Scope.APP)

            @provide(scope=Scope.APP)
            def get_resend(self) -> ResendService:
                return resend.service()

        container = make_async_container(RabbitmqProvider(), TestResendProvider())
        containers.append(container)
        await LettersConsumer(container, await container.get(RabbitmqConnection)).start()

    yield start
    for container in containers:
        await container.close()


async def publish(channel: AbstractChannel, body: dict[str, object]) -> None:
    exchange = await channel.declare_exchange(
        cfg.letters.exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await exchange.publish(
        aio_pika.Message(json.dumps(body).encode(), message_id=str(body["message_id"])),
        routing_key=cfg.letters.transactional_routing_key,
    )


async def wait_for(condition: Callable[[], bool], timeout: float = 10) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError
        await asyncio.sleep(0.05)


@pytest.mark.case(id="LETTERS-FLOW-001")
async def test_letter_reaches_provider_and_is_acknowledged(
    channel: AbstractChannel, start_worker: Callable[[FakeResend], Awaitable[None]]
) -> None:
    resend = FakeResend()
    await start_worker(resend)

    await publish(channel, letter_body(message_id="flow-1"))
    await wait_for(lambda: len(resend.requests) == 1)

    queue = await channel.declare_queue(cfg.letters.transactional_queue, passive=True)
    await asyncio.sleep(0.2)
    assert queue.declaration_result.message_count == 0
    assert resend.requests[0].headers["idempotency-key"] == "flow-1"
    assert resend.payloads()[0]["to"] == ["user@example.com"]


@pytest.mark.case(id="LETTERS-FLOW-002")
async def test_temporary_failures_are_retried_then_dead_lettered(
    channel: AbstractChannel,
    start_worker: Callable[[FakeResend], Awaitable[None]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg.letters, "max_attempts", 2)
    resend = FakeResend(statuses=[503])
    await start_worker(resend)
    dead = await channel.declare_queue(f"{cfg.letters.transactional_queue}.dead", passive=True)
    await dead.purge()

    await publish(channel, letter_body(message_id="flow-2"))
    await wait_for(lambda: len(resend.requests) == 2)

    message = None
    for _ in range(100):
        message = await dead.get(no_ack=True, fail=False)
        if message is not None:
            break
        await asyncio.sleep(0.05)
    assert message is not None
    assert json.loads(message.body)["message_id"] == "flow-2"
    assert len(resend.requests) == 2
