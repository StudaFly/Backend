"""
Unit tests for the async Claude client wrapper and the JSON response parser.
The Anthropic SDK client is mocked — no network call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.app.services.ai import client as ai_client
from src.app.services.ai.parsing import parse_json_object


def _response(stop_reason="end_turn", blocks=None):
    return SimpleNamespace(stop_reason=stop_reason, content=blocks or [])


def _mock_sdk(response):
    sdk = MagicMock()
    sdk.beta.messages.create = AsyncMock(return_value=response)
    return sdk


@pytest.mark.asyncio
async def test_call_returns_text_blocks_only():
    sdk = _mock_sdk(
        _response(
            blocks=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text='{"tasks": '),
                SimpleNamespace(type="text", text="[]}"),
            ]
        )
    )
    with patch.object(ai_client, "get_client", return_value=sdk):
        result = await ai_client.call("prompt", system="system")

    assert result == '{"tasks": []}'
    kwargs = sdk.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == ai_client.settings.ANTHROPIC_MODEL
    assert kwargs["system"] == "system"
    assert kwargs["fallbacks"] == "default"
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]


@pytest.mark.asyncio
async def test_call_raises_on_refusal():
    sdk = _mock_sdk(_response(stop_reason="refusal"))
    with (
        patch.object(ai_client, "get_client", return_value=sdk),
        pytest.raises(ai_client.AIRefusalError),
    ):
        await ai_client.call("prompt")


def test_parse_json_object_plain():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_with_code_fence_and_text():
    raw = 'Here you go:\n```json\n{"tasks": [{"title": "x"}]}\n```\nGood luck!'
    assert parse_json_object(raw) == {"tasks": [{"title": "x"}]}


@pytest.mark.parametrize("raw", ["no json here", "[1, 2]", "{broken"])
def test_parse_json_object_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_json_object(raw)
