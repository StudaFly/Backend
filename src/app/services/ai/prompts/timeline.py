from src.app.services.ai.prompts.base import build_context

SYSTEM = (
    "You are an assistant specialized in international student mobility. "
    "You generate timelines with precise deadlines. "
    "Always respond with valid JSON."
)


def build(destination: str, mobility_type: str, departure_date: str) -> str:
    context = build_context(destination, mobility_type, departure_date)
    return (
        f"{context}\n\n"
        "Generate a preparation timeline with absolute deadlines calculated "
        f"from the departure date {departure_date}. "
        "Return a JSON with the structure: "
        '{"milestones": [{"title": "...", "deadline": "YYYY-MM-DD", '
        '"category": "...", "description": "..."}]}'
    )
