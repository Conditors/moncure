
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.products import Product


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    def add(self, product: Product) -> None:
        self._session.add(product)

    async def get_by_id(
        self, 
        organization_id: UUID,
        product_id: UUID,
    ) -> Product | None:
        statement = (
            select(Product)
            .where(
                (Product.organization_id == organization_id),
                (Product.id == product_id)
            )
        )
        product = await self._session.execute(statement)
        return product.scalar_one_or_none()


    async def get_by_normalized_url(
        self,
        organization_id: UUID,
        normalized_url: str,
    ) -> Product | None:
        statement = (
            select(Product)
            .where(
                (Product.organization_id == organization_id),
                (Product.normalized_url == normalized_url)
            )
        )
        product = await self._session.execute(statement)
        return product.scalar_one_or_none()

    async def change_competitor_price_version(self, organization_id: UUID, product_id: UUID) -> int:
        statement = (
            update(Product)
            .where(
                Product.id == product_id,
                Product.organization_id == organization_id,
            )
            .values(competitor_prices_version = Product.competitor_prices_version + 1)
            .returning(Product.competitor_prices_version)
        )
        result = await self._session.execute(statement)
        new_version = result.scalar_one()
        return new_version
