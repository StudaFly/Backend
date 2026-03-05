from pydantic import BaseModel


class GuideSection(BaseModel):
    title: str
    content: str


class GuideContent(BaseModel):
    destination_id: str
    city: str
    country: str
    sections: list[GuideSection]
    emergency_contacts: dict[str, str] = {}
    useful_apps: list[str] = []
