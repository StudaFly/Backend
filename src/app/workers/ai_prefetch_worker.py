from src.app.services.ai import ai_service


async def prefetch_for_mobility(
    destination_city: str,
    destination_country: str,
    mobility_type: str,
    departure_date: str,
) -> None:
    await ai_service.generate_checklist(destination_city, mobility_type, departure_date)
    await ai_service.generate_timeline(destination_city, mobility_type, departure_date)
    await ai_service.generate_budget(destination_city, destination_country)
    await ai_service.generate_guide(destination_city, destination_country)
