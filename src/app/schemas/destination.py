import uuid

from pydantic import Field

from src.app.schemas.common import StudaFlyBaseModel


class DestinationFacts(StudaFlyBaseModel):
    language: str | None = None
    currency: str | None = None
    climate: str | None = None
    visa_required: bool | None = None
    international_students: int | None = None


class DestinationCreate(StudaFlyBaseModel):
    country: str
    country_code: str = Field(pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alpha-2")
    city: str
    image_url: str | None = None
    summary: str | None = None
    facts: DestinationFacts | None = None


class DestinationRead(StudaFlyBaseModel):
    id: uuid.UUID
    country: str
    country_code: str | None = None
    city: str
    image_url: str | None = None
    summary: str | None = None


class DestinationDetail(DestinationRead):
    facts: DestinationFacts | None = None
    has_budget: bool = False
    has_guide: bool = False
