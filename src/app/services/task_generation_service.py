"""Builds the initial task list (the "parcours") of a mobility.

The base is a static template file with deadlines computed from the departure
date, so the parcours works without the Claude API (degraded mode). When
AI_TASK_GENERATION_ENABLED is on, the AI checklist is tried first and the
templates stay the fallback.

Timeline and checklist both read this single task list.
"""

import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.config import settings
from src.app.models.destination import Destination
from src.app.models.mobility import Mobility
from src.app.models.task import Task
from src.app.services.ai import ai_service
from src.app.services.ai.parsing import parse_json_object

logger = logging.getLogger(__name__)

TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "data" / "task_templates.json"
VALID_CATEGORIES = {"admin", "finance", "housing", "health", "practical"}


@lru_cache(maxsize=1)
def load_templates() -> dict:
    with open(TEMPLATES_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_deadline(departure_date: date, days_before_departure: int, today: date) -> date:
    deadline = departure_date - timedelta(days=days_before_departure)
    if days_before_departure > 0 and deadline < today <= departure_date:
        return today
    return deadline


def _destination_zone(country: str, zones: dict[str, list[str]]) -> str:
    return "eu" if country in zones.get("eu", []) else "non_eu"


def _template_applies(template: dict, mobility_type: str, zone: str) -> bool:
    types = template.get("mobility_types")
    if types and mobility_type not in types:
        return False
    template_zone = template.get("zone")
    return template_zone is None or template_zone == zone


def build_template_tasks(
    mobility_id: UUID,
    mobility_type: str,
    departure_date: date,
    country: str,
    today: date | None = None,
) -> list[Task]:
    today = today or date.today()
    templates = load_templates()
    zone = _destination_zone(country, templates.get("zones", {}))
    return [
        Task(
            mobility_id=mobility_id,
            title=template["title"],
            description=template.get("description"),
            category=template["category"],
            deadline=compute_deadline(departure_date, template["days_before_departure"], today),
            is_completed=False,
            priority=template["priority"],
        )
        for template in templates["tasks"]
        if _template_applies(template, mobility_type, zone)
    ]


def _normalize_ai_priority(value) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 2
    if priority <= 1:
        return 1
    return 2 if priority <= 3 else 3


async def _build_ai_tasks(mobility: Mobility, destination: Destination) -> list[Task]:
    raw = await ai_service.generate_checklist(
        destination=f"{destination.city}, {destination.country}",
        mobility_type=mobility.type,
        departure_date=mobility.departure_date.isoformat(),
    )
    tasks = []
    for item in parse_json_object(raw).get("tasks", []):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        category = item.get("category")
        weeks_before = item.get("deadline_weeks_before")
        deadline = None
        if isinstance(weeks_before, int | float):
            deadline = compute_deadline(
                mobility.departure_date, int(weeks_before) * 7, date.today()
            )
        tasks.append(
            Task(
                mobility_id=mobility.id,
                title=title[:255],
                description=item.get("description"),
                category=category if category in VALID_CATEGORIES else "practical",
                deadline=deadline,
                is_completed=False,
                priority=_normalize_ai_priority(item.get("priority")),
            )
        )
    return tasks


async def build_tasks(mobility: Mobility, destination: Destination) -> list[Task]:
    if settings.AI_TASK_GENERATION_ENABLED:
        try:
            tasks = await _build_ai_tasks(mobility, destination)
            if tasks:
                return tasks
            logger.warning("AI returned no task for mobility %s, using templates", mobility.id)
        except Exception:
            logger.exception(
                "AI task generation failed for mobility %s, using templates", mobility.id
            )

    return build_template_tasks(
        mobility_id=mobility.id,
        mobility_type=mobility.type,
        departure_date=mobility.departure_date,
        country=destination.country,
    )


async def ensure_tasks(db: AsyncSession, mobility: Mobility) -> None:
    count = await db.scalar(select(func.count(Task.id)).where(Task.mobility_id == mobility.id))
    if count:
        return
    db.add_all(await build_tasks(mobility, mobility.destination))
    await db.commit()
