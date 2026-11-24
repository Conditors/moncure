from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.competitor_offer import CompetitorOffer

class CompetitorOfferRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    def add(self, competitor_offer: CompetitorOffer) -> None:
        self._session.add(competitor_offer)

    async def get_by_normalized_url(
        self,
        organization_id: UUID,
        product_id: UUID,
        normalized_url: str
    ) -> CompetitorOffer | None:
        statement = (
            select(CompetitorOffer)
            .where(
                (CompetitorOffer.organization_id == organization_id),
                (CompetitorOffer.product_id == product_id),
                (CompetitorOffer.normalized_url == normalized_url),
            )
        )
        offer = await self._session.execute(statement)
        return offer.scalar_one_or_none()
