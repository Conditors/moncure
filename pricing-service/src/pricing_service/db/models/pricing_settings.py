
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from pricing_service.db.models.base import Base
from pricing_service.db.models.mixins import CreatedAtMixin, UpdatedAtMixin, UuidPrimaryKeyMixin


class PricingSettings(Base, UuidPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "pricing_settings"

    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True, nullable=False)

    variable_costs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    allocated_fixed_costs: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    target_profit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    percent_fees: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.0000"), nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    undercut_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    current_version: Mapped[int] = mapped_column(default=1, nullable=False)