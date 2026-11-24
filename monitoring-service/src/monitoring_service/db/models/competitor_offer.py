from enum import StrEnum
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger, Boolean,
    Numeric, String,
    Text, Uuid, DateTime,
    Enum as SAEnum,
    CheckConstraint, UniqueConstraint,
    ForeignKeyConstraint,
    text, true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.mixins import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from monitoring_service.db.models.collection_jobs import CollectionJob
    from monitoring_service.db.models.price_observations import PriceObservation
    from monitoring_service.db.models.products import Product

class CompetitorAvailabilityStatus(StrEnum):
    AVAILABLE = 'available'
    OUT_OF_STOCK = 'out_of_stock'
    UNAVAILABLE = 'unavailable'


class CompetitorOffer(
    Base,
    UuidPrimaryKeyMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
):
    __tablename__ = "competitor_offers"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    article: Mapped[str | None] = mapped_column(String(55), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_price_version: Mapped[int] = mapped_column(
        BigInteger,
        server_default=text("1"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    availability_status: Mapped[CompetitorAvailabilityStatus] = mapped_column(
        SAEnum(
        CompetitorAvailabilityStatus,
        name="competitor_availability_status",
        values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="competitor_offers",
        lazy="raise"
    )
    collection_jobs: Mapped[list["CollectionJob"]] = relationship(
        "CollectionJob",
        back_populates="competitor_offer",
        lazy="raise",
        overlaps="batch,collection_jobs",
    )
    price_observations: Mapped[list["PriceObservation"]] = relationship(
        "PriceObservation",
        back_populates="competitor_offer",
        lazy="raise",
        overlaps="collection_job,price_observation",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_competitor_offers_organization_id_id"),
        UniqueConstraint("organization_id", "product_id", "id", name="uq_competitor_offers_organization_product_id"),
        UniqueConstraint("organization_id", "product_id", "normalized_url", name="uq_competitor_offers_product_url"),
        ForeignKeyConstraint(
            ("organization_id", "product_id"),
            ("products.organization_id", "products.id"),
            name="fk_competitor_offers_product",
        ),
        CheckConstraint("current_price > 0", name="ck_competitor_offers_price_positive"),
        CheckConstraint("current_price_version > 0", name="ck_competitor_offers_price_version"),
        CheckConstraint("article IS NULL OR source IS NOT NULL", name="ck_competitor_offers_article_source"),
        CheckConstraint(
            "octet_length(normalized_url) <= 2000",
            name="ck_competitor_offers_normalized_url_length",
        ),
    )
