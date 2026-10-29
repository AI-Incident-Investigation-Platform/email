from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

BASE_DIR = Path(__file__).parent.parent.parent
TOML_SETTINGS_PATH = BASE_DIR / "config.toml"

PATHS_SOURCES: list[tuple[Path, type[PydanticBaseSettingsSource]]] = [
    (TOML_SETTINGS_PATH, TomlConfigSettingsSource),
]


class Service(BaseModel):
    name: str = "email"
    port: int = 8002
    bind_host: str = "127.0.0.1"


class Rabbitmq(BaseModel):
    url: str = ""
    connect_timeout_seconds: float = Field(default=5, gt=0)
    reconnect_delay_seconds: float = Field(default=5, gt=0)


class Letters(BaseModel):
    exchange: str = "email"
    retry_exchange: str = "email.retry"
    dead_exchange: str = "email.dead"
    transactional_routing_key: str = "send.transactional"
    transactional_queue: str = "email.transactional"
    # задачи в работе на под: Resend отвечает за сотни миллисекунд, а квота провайдера невелика
    prefetch: int = Field(default=8, ge=1)
    max_attempts: int = Field(default=5, ge=1)
    retry_delay_seconds: int = Field(default=10, ge=1)
    dead_letter_ttl_days: int = Field(default=7, ge=1)


class Resend(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.resend.com"
    timeout_seconds: float = Field(default=10, gt=0)
    from_address: str = ""
    # квоты аккаунта Resend; воркер не превышает ни свои, ни лимиты из ответа провайдера
    requests_per_second: float = Field(default=10, gt=0)
    daily_quota: int = Field(default=100, ge=1)
    monthly_quota: int = Field(default=3000, ge=1)
    usage_refresh_seconds: float = Field(default=60, gt=0)


class Tracing(BaseModel):
    enabled: bool = True
    otlp_endpoint: str = ""


class Logging(BaseModel):
    level: str = "INFO"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        toml_file=TOML_SETTINGS_PATH,
        env_nested_delimiter="__",
    )

    service: Service = Service()
    rabbitmq: Rabbitmq = Rabbitmq()
    letters: Letters = Letters()
    resend: Resend = Resend()
    tracing: Tracing = Tracing()
    logging: Logging = Logging()

    def missing_required(self) -> list[str]:
        required = {
            "rabbitmq.url": self.rabbitmq.url,
            "resend.api_key": self.resend.api_key,
            "resend.from_address": self.resend.from_address,
        }
        if self.tracing.enabled:
            required["tracing.otlp_endpoint"] = self.tracing.otlp_endpoint
        return [name for name, value in required.items() if not value]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        active_sources = [method(settings_cls) for path, method in PATHS_SOURCES if path.exists()]
        return EnvSettingsSource(settings_cls), *active_sources


cfg = Config()
