from enum import StrEnum
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import (
    Index,
    String,
    Text, Uuid,
    Enum as SAEnum,
    CheckConstraint, UniqueConstraint,
    ForeignKeyConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitoring_service.db.models.base import Base
from monitoring_service.db.models.mixins import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UuidPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from monitoring_service.db.models.products import Product
    
class ImportJobType(StrEnum):
    OWN_PRODUCT_IMPORT = 'own_product_import'
    COMPETITOR_OFFER_IMPORT = 'competitor_offer_import'

class ImportJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"
    FAILED = "failed"

class ImportJob(
    Base,
    UuidPrimaryKeyMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
):
    __tablename__ = "import_jobs"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    target_product_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    job_type: Mapped[ImportJobType] = mapped_column(
        SAEnum(
        ImportJobType,
        name="import_job_type",
        values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False
    )
    status: Mapped[ImportJobStatus] = mapped_column(
        SAEnum(
            ImportJobStatus,
            name="import_job_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        server_default=ImportJobStatus.PENDING.value,
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    draft_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    target_product: Mapped["Product | None"] = relationship(
        "Product",
        back_populates="import_jobs",
        lazy="raise",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ("organization_id", "target_product_id"),
            ("products.organization_id", "products.id"),
            name="fk_import_jobs_target_product",
        ),
        CheckConstraint(
            """
            (
                job_type = 'own_product_import'
                AND target_product_id IS NULL
            )
            OR
            (
                job_type = 'competitor_offer_import'
                AND target_product_id IS NOT NULL
            )
            """,
            name="ck_import_jobs_target_product",
        ),
        Index(
            "idx_import_jobs_organization_status_created",
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
    )
