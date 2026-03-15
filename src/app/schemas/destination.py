import uuid

from src.app.schemas.common import StudaFlyBaseModel


class DestinationCreate(StudaFlyBaseModel):
    country: str
    city: str
    image_url: str | None = None
    guide_content: dict | None = None
    cost_of_living: dict | None = None


class DestinationUpdate(StudaFlyBaseModel):
    country: str | None = None
    city: str | None = None
    image_url: str | None = None
    guide_content: dict | None = None
    cost_of_living: dict | None = None


class DestinationRead(StudaFlyBaseModel):
    id: uuid.UUID
    country: str
    city: str
    image_url: str | None = None
    guide_content: dict | None = None
    cost_of_living: dict | None = None
