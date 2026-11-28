from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox


class RabbitMQOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, event: RabbitMqOutbox) -> None:
        self._session.add(event)


    async def get_unpublished_batch(self, limit: int) -> list[RabbitMqOutbox]:
        statement = (
            select(RabbitMqOutbox)
            .where(RabbitMqOutbox.published_at.is_(None))
            .order_by(RabbitMqOutbox.occurred_at, RabbitMqOutbox.event_id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        events = await self._session.execute(statement)
        return list(events.scalars().all())

    async def mark_published(self, event: RabbitMqOutbox, published_at: datetime):
        event.published_at = published_at
        await self._session.flush()

