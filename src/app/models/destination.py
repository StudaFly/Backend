import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base

if TYPE_CHECKING:
    from src.app.models.mobility import Mobility


class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_of_living: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    guide_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    mobilities: Mapped[list["Mobility"]] = relationship("Mobility", back_populates="destination")
