import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import field_validator

from src.app.schemas.common import StudaFlyBaseModel

MobilityType = Literal["erasmus", "stage", "semestre", "double_diplome"]
MobilityStatus = Literal["preparing", "departed", "completed"]


class MobilityCreate(StudaFlyBaseModel):
    destination_id: uuid.UUID
    type: MobilityType
    departure_date: date
    return_date: date | None = None
    school: str | None = None

    @field_validator("departure_date", mode="before")
    @classmethod
    def validate_departure_date_format(cls, v) -> date:
        if isinstance(v, str):
            parts = v.split("-")
            if len(parts) != 3 or len(parts[0]) != 4 or not all(p.isdigit() for p in parts):
                raise ValueError("departureDate must be in ISO 8601 format (YYYY-MM-DD)")
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError("departureDate must be in ISO 8601 format (YYYY-MM-DD)")
        return v


class MobilityRead(StudaFlyBaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    destination_id: uuid.UUID
    type: str
    departure_date: date
    return_date: date | None
    status: str
    school: str | None = None
    created_at: datetime


class MobilityUpdate(StudaFlyBaseModel):
    type: MobilityType | None = None
    departure_date: date | None = None
    return_date: date | None = None
    status: MobilityStatus | None = None
    school: str | None = None
