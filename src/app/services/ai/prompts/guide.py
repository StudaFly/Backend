SYSTEM = (
    "You are an expert guide for international students on mobility programs. "
    "Your advice is practical, culturally sensitive, and tailored to students. "
    "Always respond with valid JSON."
)


def build(city: str, country: str) -> str:
    return (
        f"City: {city}, Country: {country}\n\n"
        "Generate a comprehensive guide for a student arriving in this city. "
        "Cover: local culture, transportation, health, housing, tips, emergency contacts. "
        "Return a JSON with the structure: "
        '{"sections": [{"title": "...", "content": "..."}], '
        '"emergency_contacts": {"Police": "...", "Ambulance": "..."}, '
        '"useful_apps": ["..."]}'
    )
