from datetime import datetime
from enum import StrEnum
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
    Enum as SAEnum,
    CheckConstraint,
    ForeignKeyConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.mixins import (
    CreatedAtMixin,
    UuidPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from monitoring_service.db.models.collection_jobs import CollectionJob
    from monitoring_service.db.models.products import Product

class CollectionBatchTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class CollectionBatchStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

class CollectionBatch(
    Base,
    UuidPrimaryKeyMixin,
    CreatedAtMixin, 
):
    __tablename__ = "collection_batches"

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    trigger_type: Mapped[CollectionBatchTriggerType] = mapped_column(
        SAEnum(
            CollectionBatchTriggerType,
            name="collection_trigger_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[CollectionBatchStatus] = mapped_column(
        SAEnum(
            CollectionBatchStatus,
            name="collection_batch_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        server_default=CollectionBatchStatus.PENDING.value,
        nullable=False,
    )
    total_jobs: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_jobs: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    succeeded_jobs: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    failed_jobs: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    changed_jobs: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped["Product"] = relationship(
        "Product",
        back_populates="collection_batches",
        lazy="raise",
    )
    collection_jobs: Mapped[list["CollectionJob"]] = relationship(
        "CollectionJob",
        back_populates="batch",
        lazy="raise",
        overlaps="collection_jobs,competitor_offer",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_collection_batches_organization_id_id"),
        UniqueConstraint(
            "organization_id",
            "id",
            "product_id",
            name="uq_collection_batches_organization_product_id",
        ),
        ForeignKeyConstraint(
            ("organization_id", "product_id"),
            ("products.organization_id", "products.id"),
            name="fk_collection_batches_product",
        ),
        CheckConstraint("total_jobs > 0", name="ck_collection_batches_total_jobs"),
        CheckConstraint(
            """
            completed_jobs >= 0
            AND completed_jobs <= total_jobs
            """,
            name="ck_collection_batches_completed_jobs"
        ),
        CheckConstraint(
            """
            succeeded_jobs >= 0
            AND succeeded_jobs <= completed_jobs
            """,
            name="ck_collection_batches_succeeded_jobs"
        ),
        CheckConstraint(
            """
            failed_jobs >= 0
            AND failed_jobs <= completed_jobs
            """,
            name="ck_collection_batches_failed_jobs"
        ),
        CheckConstraint("succeeded_jobs + failed_jobs = completed_jobs", name="ck_collection_batches_completed_sum"),
        CheckConstraint(
            """
            changed_jobs >= 0
            AND changed_jobs <= succeeded_jobs
            """,
            name="ck_collection_batches_changed_jobs"
        ),
        Index(
            "uq_collection_batches_active_product",
            "organization_id",
            "product_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        Index(
            "idx_collection_batches_request",
            "organization_id",
            "request_id",
            "id",
        ),

        Index(
            "idx_collection_batches_product_created",
            "organization_id",
            "product_id",
            "created_at",
            "id",
        ),

        Index(
            "idx_collection_batches_status_created",
            "status",
            "created_at",
            "id",
        ),
    )
