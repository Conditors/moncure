from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.price_observations import PriceObservation

class PriceObservationsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    def add(self, price_observation: PriceObservation) -> None:
        self._session.add(price_observation)