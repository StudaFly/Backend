from src.app.services.ai.prompts.base import build_context

SYSTEM = (
    "You are an assistant specialized in international student mobility. "
    "You generate personalized, precise, and actionable checklists. "
    "Always respond with valid JSON."
)


def build(destination: str, mobility_type: str, departure_date: str) -> str:
    context = build_context(destination, mobility_type, departure_date)
    return (
        f"{context}\n\n"
        "Generate a personalized checklist for this mobility. "
        "Return a JSON with the structure: "
        '{"tasks": [{"title": "...", "category": "admin|finance|housing|health|practical", '
        '"priority": 1-5, "deadline_weeks_before": 0-26, "description": "..."}]}'
    )
