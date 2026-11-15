from decimal import Decimal
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Numeric, String,
    Text, Uuid,
    CheckConstraint, Index, UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.mixins import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from monitoring_service.db.models.competitor_offer import CompetitorOffer
    from monitoring_service.db.models.import_job import ImportJob
    from monitoring_service.db.models.collection_batches import CollectionBatch

class Product(
    UuidPrimaryKeyMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
    Base,
):
    __tablename__ = "products"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    article: Mapped[str | None] = mapped_column(String(55), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    competitor_prices_version: Mapped[int] = mapped_column(
        BigInteger,
        server_default=text("0"),
        nullable=False,
    )

    competitor_offers: Mapped[list["CompetitorOffer"]] = relationship(
        "CompetitorOffer",
        back_populates="product",
        lazy="raise",
    )
    import_jobs: Mapped[list["ImportJob"]] = relationship(
        "ImportJob",
        back_populates="target_product",
        lazy="raise",
    )

    collection_batches: Mapped[list["CollectionBatch"]] = relationship(
        "CollectionBatch",
        back_populates="product",
        lazy="raise",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_products_organization_id_id"),
        CheckConstraint("price > 0", name="ck_products_price_positive"),
        CheckConstraint(
            "competitor_prices_version >= 0",
            name="ck_products_competitor_prices_version",
        ),
        CheckConstraint(
            "article IS NULL OR source IS NOT NULL",
            name="ck_products_article_source",
        ),
        Index(
            "idx_products_organization_created",
            "organization_id",
            "created_at",
            "id",
        ),
    )
