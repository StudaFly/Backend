from src.app.services.ai import cache as ai_cache
from src.app.services.ai import client as ai_client
from src.app.services.ai.prompts import budget as budget_prompts
from src.app.services.ai.prompts import checklist as checklist_prompts
from src.app.services.ai.prompts import day_zero as day_zero_prompts
from src.app.services.ai.prompts import guide as guide_prompts
from src.app.services.ai.prompts import timeline as timeline_prompts


async def generate_checklist(destination: str, mobility_type: str, departure_date: str) -> str:
    params = {"destination": destination, "type": mobility_type, "date": departure_date}
    cached = await ai_cache.get_cached("checklist", params)
    if cached:
        return cached
    prompt = checklist_prompts.build(destination, mobility_type, departure_date)
    result = await ai_client.call(prompt, system=checklist_prompts.SYSTEM)
    await ai_cache.set_cached("checklist", params, result)
    return result


async def generate_timeline(destination: str, mobility_type: str, departure_date: str) -> str:
    params = {"destination": destination, "type": mobility_type, "date": departure_date}
    cached = await ai_cache.get_cached("timeline", params)
    if cached:
        return cached
    prompt = timeline_prompts.build(destination, mobility_type, departure_date)
    result = await ai_client.call(prompt, system=timeline_prompts.SYSTEM)
    await ai_cache.set_cached("timeline", params, result)
    return result


async def generate_budget(city: str, country: str) -> str:
    params = {"city": city, "country": country}
    cached = await ai_cache.get_cached("budget", params)
    if cached:
        return cached
    prompt = budget_prompts.build(city, country)
    result = await ai_client.call(prompt, system=budget_prompts.SYSTEM)
    await ai_cache.set_cached("budget", params, result)
    return result


async def generate_guide(city: str, country: str) -> str:
    params = {"city": city, "country": country}
    cached = await ai_cache.get_cached("guide", params)
    if cached:
        return cached
    prompt = guide_prompts.build(city, country)
    result = await ai_client.call(prompt, system=guide_prompts.SYSTEM)
    await ai_cache.set_cached("guide", params, result)
    return result


async def generate_day_zero(city: str, country: str, mobility_type: str) -> str:
    params = {"city": city, "country": country, "type": mobility_type}
    cached = await ai_cache.get_cached("day_zero", params)
    if cached:
        return cached
    prompt = day_zero_prompts.build(city, country, mobility_type)
    result = await ai_client.call(prompt, system=day_zero_prompts.SYSTEM)
    await ai_cache.set_cached("day_zero", params, result)
    return result
