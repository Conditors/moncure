from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from monitoring_service.db.repositories.advisory_lock import PostgresAdvisoryLock
from monitoring_service.db.repositories.competitor_offer import CompetitorOfferRepository
from monitoring_service.db.repositories.import_job import ImportJobRepository
from monitoring_service.db.repositories.product import ProductRepository
from monitoring_service.db.repositories.rabbitmq_inbox import InboxRepository
from monitoring_service.db.repositories.rabbitmq_outbox import RabbitMQOutboxRepository


class UnitOfWork:

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
    
    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.advisory_lock = PostgresAdvisoryLock(self._session)
        self.import_jobs = ImportJobRepository(self._session)
        self.products = ProductRepository(self._session)
        self.competitors = CompetitorOfferRepository(self._session)
        self.inbox = InboxRepository(self._session)
        self.outbox = RabbitMQOutboxRepository(self._session)

        return self


    async def __aexit__(
        self, 
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._session.rollback()

        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def flush(self) -> None:
        await self._session.flush()
