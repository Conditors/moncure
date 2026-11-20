
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox


class RabbitMQOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: RabbitMqOutbox) -> None:
        self._session.add(event)
