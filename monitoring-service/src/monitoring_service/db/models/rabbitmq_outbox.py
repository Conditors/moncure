
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from monitoring_service.db.models.base import Base

class RabbitMqOutbox(Base):
    __tablename__ = "rabbitmq_outbox_events"

    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid4,
        primary_key=True,
    )
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        SmallInteger,
        server_default=text("1"),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "schema_version > 0",
            name="ck_rabbitmq_outbox_schema_version",
        ),
        Index(
            "idx_rabbitmq_outbox_unpublished",
            "occurred_at",
            "event_id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


