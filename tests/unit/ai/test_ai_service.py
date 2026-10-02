"""
Unit tests for ai_service.py.
All Claude API calls and Redis cache operations are mocked.
"""

from unittest.mock import AsyncMock, patch

import pytest

TIMELINE_JSON = (
    '{"milestones": [{"title": "Apply for Erasmus", "deadline": "2025-06-01",'
    ' "category": "admin", "description": "Submit your application"}]}'
)
CHECKLIST_JSON = (
    '{"tasks": [{"title": "Get passport", "category": "admin", "priority": 2,'
    ' "deadline_weeks_before": 12, "description": "Renew if needed"}]}'
)


@pytest.mark.asyncio
async def test_generate_timeline_cache_miss_calls_ai():
    with (
        patch(
            "src.app.services.ai.ai_service.ai_cache.get_cached",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.app.services.ai.ai_service.ai_client.call",
            new_callable=AsyncMock,
            return_value=TIMELINE_JSON,
        ) as mock_call,
        patch(
            "src.app.services.ai.ai_service.ai_cache.set_cached",
            new_callable=AsyncMock,
        ) as mock_set,
    ):
        from src.app.services.ai import ai_service

        result = await ai_service.generate_timeline("Barcelona, Spain", "erasmus", "2025-09-01")

        assert result == TIMELINE_JSON
        mock_call.assert_called_once()
        mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_generate_timeline_cache_hit_skips_ai():
    with (
        patch(
            "src.app.services.ai.ai_service.ai_cache.get_cached",
            new_callable=AsyncMock,
            return_value=TIMELINE_JSON,
        ),
        patch(
            "src.app.services.ai.ai_service.ai_client.call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        from src.app.services.ai import ai_service

        result = await ai_service.generate_timeline("Barcelona, Spain", "erasmus", "2025-09-01")

        assert result == TIMELINE_JSON
        mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_generate_checklist_cache_miss_calls_ai():
    with (
        patch(
            "src.app.services.ai.ai_service.ai_cache.get_cached",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.app.services.ai.ai_service.ai_client.call",
            new_callable=AsyncMock,
            return_value=CHECKLIST_JSON,
        ) as mock_call,
        patch(
            "src.app.services.ai.ai_service.ai_cache.set_cached",
            new_callable=AsyncMock,
        ),
    ):
        from src.app.services.ai import ai_service

        result = await ai_service.generate_checklist("Berlin, Germany", "stage", "2025-06-15")

        assert result == CHECKLIST_JSON
        mock_call.assert_called_once()


@pytest.mark.asyncio
async def test_generate_checklist_cache_hit_skips_ai():
    with (
        patch(
            "src.app.services.ai.ai_service.ai_cache.get_cached",
            new_callable=AsyncMock,
            return_value=CHECKLIST_JSON,
        ),
        patch(
            "src.app.services.ai.ai_service.ai_client.call",
            new_callable=AsyncMock,
        ) as mock_call,
    ):
        from src.app.services.ai import ai_service

        result = await ai_service.generate_checklist("Berlin, Germany", "stage", "2025-06-15")

        assert result == CHECKLIST_JSON
        mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_generate_timeline_uses_correct_params_for_cache_key():
    call_count = 0

    async def fake_get_cached(prefix, params):
        return None

    async def fake_call(prompt, system="", max_tokens=2048):
        nonlocal call_count
        call_count += 1
        return TIMELINE_JSON

    async def fake_set_cached(prefix, params, value):
        pass

    with (
        patch("src.app.services.ai.ai_service.ai_cache.get_cached", side_effect=fake_get_cached),
        patch("src.app.services.ai.ai_service.ai_client.call", side_effect=fake_call),
        patch("src.app.services.ai.ai_service.ai_cache.set_cached", side_effect=fake_set_cached),
    ):
        from src.app.services.ai import ai_service

        await ai_service.generate_timeline("Barcelona, Spain", "erasmus", "2025-09-01")
        await ai_service.generate_timeline("Berlin, Germany", "stage", "2025-06-15")

    assert call_count == 2
