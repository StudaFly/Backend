from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import NotFoundError
from src.app.models.destination import Destination
from src.app.schemas.guide import GuideContent, GuideSection, GuideStep

_SECTION_TITLES = {
    "overview": "Présentation",
    "housing": "Logement",
    "transport": "Transports",
    "health": "Santé",
    "culture": "Culture",
}


async def get_guide(db: AsyncSession, destination_id: UUID) -> GuideContent:
    destination = await db.get(Destination, destination_id)
    if not destination:
        raise NotFoundError("Destination not found")
    content = destination.guide_content
    if not content:
        raise NotFoundError("No guide available for this destination")

    sections = [
        GuideSection(key=key, title=title, content=content[key])
        for key, title in _SECTION_TITLES.items()
        if isinstance(content.get(key), str) and content[key].strip()
    ]
    contacts = content.get("useful_contacts") or {}
    return GuideContent(
        destination_id=destination.id,
        city=destination.city,
        country=destination.country,
        sections=sections,
        tips=[tip for tip in content.get("tips") or [] if isinstance(tip, str)],
        key_steps=[
            GuideStep(title=step["title"], description=step["description"], timing=step["timing"])
            for step in content.get("key_steps") or []
            if isinstance(step, dict) and {"title", "description", "timing"} <= step.keys()
        ],
        emergency_contacts={k: str(v) for k, v in contacts.items()},
        useful_apps=[app for app in content.get("useful_apps") or [] if isinstance(app, str)],
    )
