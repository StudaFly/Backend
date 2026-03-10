from src.app.schemas.common import StudaFlyBaseModel


class GuideSection(StudaFlyBaseModel):
    title: str
    content: str


class GuideContent(StudaFlyBaseModel):
    destination_id: str
    city: str
    country: str
    sections: list[GuideSection]
    emergency_contacts: dict[str, str] = {}
    useful_apps: list[str] = []
