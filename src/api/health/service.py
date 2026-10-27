from src.core.rabbitmq.connection import RabbitmqConnection
from src.core.rabbitmq.exc import BrokerUnavailableError


class HealthService:
    def __init__(self, connection: RabbitmqConnection) -> None:
        self._connection = connection

    async def check_ready(self) -> None:
        if not self._connection.is_connected:
            raise BrokerUnavailableError
