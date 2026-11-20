from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.rabbitmq_inbox import RabbitMqInbox


class InboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_add(
        self,
        event_id: UUID,
        event_type: str,
    ) -> bool:
        statement = (
            insert(RabbitMqInbox)
            .values(
                event_id=event_id, 
                event_type=event_type,
                )
            .on_conflict_do_nothing(
                index_elements=[
                    RabbitMqInbox.event_id,
                ],
            )
            .returning(RabbitMqInbox.event_id)
        )

        result = await self._session.execute(statement)
        inserted_event_id = result.scalar_one_or_none()
        return inserted_event_id is not None