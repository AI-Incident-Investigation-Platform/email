import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider
from dishka.integrations.fastapi import setup_dishka as setup_fastapi_dishka
from fastapi import FastAPI

from src.api.exc.handler import ApiErrorHandler
from src.api.health.router import router as health_router
from src.api.metrics.router import router as metrics_router
from src.config import cfg
from src.config.exc import ConfigIncompleteError
from src.core.di import HealthProvider, LettersProvider, RabbitmqProvider, ResendProvider
from src.core.logging import setup_logging
from src.core.rabbitmq.connection import RabbitmqConnection
from src.core.tracing import setup_tracing, shutdown_tracing
from src.worker.letters.consumer import LettersConsumer

log = logging.getLogger(__name__)

container = make_async_container(
    FastapiProvider(),
    RabbitmqProvider(),
    ResendProvider(),
    LettersProvider(),
    HealthProvider(),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(cfg.logging.level)
    if missing := cfg.missing_required():
        log.critical(
            "Не заданы обязательные настройки сервиса",
            extra={"event": "service.config_incomplete", "missing_settings": missing},
        )
        raise ConfigIncompleteError({"missing_settings": missing})
    try:
        await LettersConsumer(container, await container.get(RabbitmqConnection)).start()
        log.info("Сервис готов принимать задачи", extra={"event": "service.started"})
        yield
    finally:
        log.info("Сервис останавливается", extra={"event": "service.stopping"})
        await container.close()
        shutdown_tracing()
        log.info("Сервис остановлен", extra={"event": "service.stopped"})


app = FastAPI(title="AIIP email", lifespan=lifespan)

setup_fastapi_dishka(app=app, container=container)

app.include_router(health_router)
app.include_router(metrics_router)

ApiErrorHandler.register(app)

if cfg.tracing.enabled:
    setup_tracing(app)


def main() -> None:
    uvicorn.run(
        "src.main:app",
        host=cfg.service.bind_host,
        port=cfg.service.port,
        log_config=None,
        workers=1,
    )


if __name__ == "__main__":
    main()
