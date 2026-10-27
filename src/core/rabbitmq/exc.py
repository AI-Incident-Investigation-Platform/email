from src.core.errors import IntegrationUnavailableError


class BrokerUnavailableError(IntegrationUnavailableError):
    code = "rabbitmq.unavailable"
    message = "Брокер сообщений недоступен"
