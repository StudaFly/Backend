import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

MobilityType = Literal["erasmus", "stage", "semestre", "double_diplome"]
MobilityStatus = Literal["preparing", "departed", "completed"]


class MobilityCreate(BaseModel):
    destination_id: uuid.UUID
    type: MobilityType
    departure_date: date
    return_date: date | None = None


class MobilityRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    destination_id: uuid.UUID
    type: str
    departure_date: date
    return_date: date | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MobilityUpdate(BaseModel):
    type: MobilityType | None = None
    departure_date: date | None = None
    return_date: date | None = None
    status: MobilityStatus | None = None
