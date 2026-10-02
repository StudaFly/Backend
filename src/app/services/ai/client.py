from src.app.core.config import settings

_client = None

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIRefusalError(Exception):
    pass


def get_client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or None)
    return _client


async def call(prompt: str, system: str = "", max_tokens: int = 16000) -> str:
    response = await get_client().beta.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium"},
        betas=[_FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise AIRefusalError("The AI model declined the request")
    return "".join(block.text for block in response.content if block.type == "text")
