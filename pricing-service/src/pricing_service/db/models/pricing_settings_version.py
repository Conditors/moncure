from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from pricing_service.db.models.base import Base
from pricing_service.db.models.mixins import CreatedAtMixin, UuidPrimaryKeyMixin


class PricingSettingsVersion(Base, UuidPrimaryKeyMixin, CreatedAtMixin):
    __tablename__ = "pricing_settings_versions"
    __table_args__ = (
        UniqueConstraint("settings_id", "version", name="uq_pricing_settings_version"),
    )

    settings_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pricing_settings.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    variable_costs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    allocated_fixed_costs: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    target_profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    percent_fees: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    undercut_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)