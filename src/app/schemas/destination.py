import uuid

from src.app.schemas.common import StudaFlyBaseModel


class DestinationCreate(StudaFlyBaseModel):
    country: str
    city: str


class DestinationRead(StudaFlyBaseModel):
    id: uuid.UUID
    country: str
    city: str
