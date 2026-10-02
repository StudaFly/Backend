import uuid

from src.app.schemas.common import StudaFlyBaseModel


class GuideSection(StudaFlyBaseModel):
    key: str
    title: str
    content: str


class GuideStep(StudaFlyBaseModel):
    title: str
    description: str
    timing: str


class GuideContent(StudaFlyBaseModel):
    destination_id: uuid.UUID
    city: str
    country: str
    sections: list[GuideSection]
    tips: list[str] = []
    key_steps: list[GuideStep] = []
    emergency_contacts: dict[str, str] = {}
    useful_apps: list[str] = []
