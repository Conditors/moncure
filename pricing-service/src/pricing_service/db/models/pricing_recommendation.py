from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pricing_service.db.models.base import Base
from pricing_service.db.models.mixins import CreatedAtMixin, UuidPrimaryKeyMixin


class PricingRecommendation(Base, UuidPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "pricing_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "settings_version_id",
            "sync_run_id",
            name="uq_pricing_recommendation_idempotency",
        ),
    )

    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)
    settings_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pricing_settings_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    sync_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), index=True, nullable=True)

    min_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    recommended_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expected_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    warning: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(
        String(50), default="formula_v1", nullable=False
    )

    market_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)