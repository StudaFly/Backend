from src.app.core.config import settings

_client = None

AI_MODEL = "claude-sonnet-4-5"


def get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic

        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def call(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    client = get_client()
    messages = [{"role": "user", "content": prompt}]
    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return response.content[0].text
