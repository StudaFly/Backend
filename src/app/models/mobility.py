import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base

if TYPE_CHECKING:
    from src.app.models.destination import Destination
    from src.app.models.document import Document
    from src.app.models.task import Task
    from src.app.models.user import User


class Mobility(Base):
    __tablename__ = "mobilities"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("destinations.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="preparing", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="mobilities")
    destination: Mapped["Destination"] = relationship("Destination", back_populates="mobilities")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="mobility")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="mobility")
