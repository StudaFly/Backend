SYSTEM = (
    "You are a supportive assistant for students arriving in a new country. "
    "You guide them through their first day on-site with concrete and reassuring advice. "
    "Always respond with valid JSON."
)


def build(city: str, country: str, mobility_type: str) -> str:
    return (
        f"City: {city}, Country: {country}, Mobility type: {mobility_type}\n\n"
        "Generate a Day-Zero guide for a student who has just arrived. "
        "Include: first urgent steps, how to connect, where to eat, key contacts. "
        "Return a JSON with the structure: "
        '{"checklist_day1": ["..."], "tips": ["..."], "important_numbers": {"...": "..."}}'
    )
