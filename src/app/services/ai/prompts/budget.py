SYSTEM = (
    "You are an expert in cost of living for international students on mobility programs. "
    "Your estimates are realistic and based on recent data. "
    "Always respond with valid JSON."
)


def build(city: str, country: str) -> str:
    return (
        f"City: {city}, Country: {country}\n\n"
        "Estimate the monthly budget for an international student on mobility in this city. "
        "Return a JSON with the structure: "
        '{"monthly_total_min": 0, "monthly_total_max": 0, "currency": "EUR", '
        '"breakdown": [{"label": "...", "amount_min": 0, "amount_max": 0}], '
        '"tips": ["..."]}'
    )
