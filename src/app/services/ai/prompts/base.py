def build_context(destination: str, mobility_type: str, departure_date: str) -> str:
    return (
        f"Destination: {destination}\n"
        f"Mobility type: {mobility_type}\n"
        f"Departure date: {departure_date}"
    )


def format_response(content: str) -> str:
    return content.strip()
