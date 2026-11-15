from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.competitor_offer import (
    CompetitorAvailabilityStatus,
)
from monitoring_service.db.models.mixins import UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from monitoring_service.db.models.collection_jobs import CollectionJob
    from monitoring_service.db.models.competitor_offer import CompetitorOffer


class PriceObservation(
    UuidPrimaryKeyMixin,
    Base,
):
    __tablename__ = "price_observations"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    competitor_offer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    collection_job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4),
        nullable=True,
    )
    price_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    availability_status: Mapped[CompetitorAvailabilityStatus] = mapped_column(
        SAEnum(
            CompetitorAvailabilityStatus,
            name="competitor_availability_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    competitor_offer: Mapped["CompetitorOffer"] = relationship(
        "CompetitorOffer",
        back_populates="price_observations",
        lazy="raise",
        overlaps="collection_job,price_observation",
    )
    collection_job: Mapped["CollectionJob | None"] = relationship(
        "CollectionJob",
        back_populates="price_observation",
        lazy="raise",
        overlaps="competitor_offer,price_observations",
    )

    __table_args__ = (
        UniqueConstraint(
            "collection_job_id",
            name="uq_price_observations_collection_job",
        ),
        ForeignKeyConstraint(
            ("organization_id", "competitor_offer_id"),
            (
                "competitor_offers.organization_id",
                "competitor_offers.id",
            ),
            name="fk_price_observations_offer",
        ),
        ForeignKeyConstraint(
            (
                "organization_id",
                "collection_job_id",
                "competitor_offer_id",
            ),
            (
                "collection_jobs.organization_id",
                "collection_jobs.id",
                "collection_jobs.competitor_offer_id",
            ),
            name="fk_price_observations_collection_job",
        ),
        CheckConstraint(
            "price IS NULL OR price > 0",
            name="ck_price_observations_price",
        ),
        CheckConstraint(
            "price_version > 0",
            name="ck_price_observations_price_version",
        ),
        CheckConstraint(
            """
            (price IS NULL AND currency IS NULL)
            OR
            (price IS NOT NULL AND currency IS NOT NULL)
            """,
            name="ck_price_observations_price_currency",
        ),
        Index(
            "idx_price_observations_offer_observed",
            "organization_id",
            "competitor_offer_id",
            "observed_at",
            "id",
        ),
    )
