from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.mixins import CreatedAtMixin, UuidPrimaryKeyMixin

if TYPE_CHECKING:
    from monitoring_service.db.models.collection_batches import CollectionBatch
    from monitoring_service.db.models.competitor_offer import CompetitorOffer
    from monitoring_service.db.models.price_observations import PriceObservation


class CollectionJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CollectionJob(
    UuidPrimaryKeyMixin,
    CreatedAtMixin,
    Base,
):
    __tablename__ = "collection_jobs"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    competitor_offer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    status: Mapped[CollectionJobStatus] = mapped_column(
        SAEnum(
            CollectionJobStatus,
            name="collection_job_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        server_default=CollectionJobStatus.PENDING.value,
        nullable=False,
    )
    data_changed: Mapped[bool] = mapped_column(
        Boolean,
        server_default=false(),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    batch: Mapped["CollectionBatch"] = relationship(
        "CollectionBatch",
        back_populates="collection_jobs",
        lazy="raise",
        overlaps="collection_jobs,competitor_offer",
    )
    competitor_offer: Mapped["CompetitorOffer"] = relationship(
        "CompetitorOffer",
        back_populates="collection_jobs",
        lazy="raise",
        overlaps="batch,collection_jobs",
    )
    price_observation: Mapped["PriceObservation | None"] = relationship(
        "PriceObservation",
        back_populates="collection_job",
        uselist=False,
        lazy="raise",
        overlaps="competitor_offer,price_observations",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_collection_jobs_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            "competitor_offer_id",
            name="uq_collection_jobs_organization_id_id_offer_id",
        ),
        UniqueConstraint(
            "organization_id",
            "batch_id",
            "competitor_offer_id",
            name="uq_collection_jobs_batch_offer",
        ),
        ForeignKeyConstraint(
            ("organization_id", "batch_id", "product_id"),
            (
                "collection_batches.organization_id",
                "collection_batches.id",
                "collection_batches.product_id",
            ),
            name="fk_collection_jobs_batch",
        ),
        ForeignKeyConstraint(
            ("organization_id", "product_id", "competitor_offer_id"),
            (
                "competitor_offers.organization_id",
                "competitor_offers.product_id",
                "competitor_offers.id",
            ),
            name="fk_collection_jobs_offer",
        ),
        Index(
            "idx_collection_jobs_offer_created",
            "organization_id",
            "competitor_offer_id",
            "created_at",
            "id",
        ),
        Index(
            "idx_collection_jobs_status_created",
            "status",
            "created_at",
            "id",
        ),
    )
