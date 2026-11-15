

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, Uuid, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from monitoring_service.db.models.base import Base

class RabbitMqInbox(
    Base,
):
    __tablename__ = "rabbitmq_inbox_events"

    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now() ,nullable=False)

