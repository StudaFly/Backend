import uuid

from src.app.schemas.common import StudaFlyBaseModel


class OrganizationSummary(StudaFlyBaseModel):

    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None = None
    branding: dict = {}
