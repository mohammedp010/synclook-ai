"""Unit tests for LLMService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import LLMError
from backend.services.llm import LLMService


def _disabled_service() -> LLMService:
    settings = MagicMock()
    settings.vlm_api_key = ""
    return LLMService(settings=settings)


class TestLLMService:
    """Tests for LLMService — no real API calls."""

    def test_disabled_without_api_key(self) -> None:
        assert _disabled_service().enabled is False

    def test_enabled_with_api_key(self) -> None:
        settings = MagicMock()
        settings.vlm_api_key = "sk-test-key"
        settings.vlm_base_url = "https://openrouter.ai/api/v1"
        svc = LLMService(settings=settings)
        assert svc.enabled is True

    async def test_chat_raises_when_disabled(self) -> None:
        with pytest.raises(LLMError, match="disabled"):
            await _disabled_service()._chat("system", "test prompt")

    async def test_extract_intent_raises_when_disabled(self) -> None:
        with pytest.raises(LLMError):
            await _disabled_service().extract_intent("style this for a rainy dinner under 5000")

    async def test_grounded_explanation_raises_when_disabled(self) -> None:
        with pytest.raises(LLMError):
            await _disabled_service().generate_grounded_explanation(
                facts=["Base garment: navy shirt (smart_casual)"],
                occasion="dinner",
            )

    async def test_structured_parses_the_json_schema_reply(self) -> None:
        svc = _service_with_reply('{"budget_total_inr": 5000, "climate": "rainy"}')
        intent = await svc.extract_intent("rainy dinner under 5000")
        assert intent.budget_total_inr == 5000

    async def test_structured_rejects_a_reply_that_breaks_the_schema(self) -> None:
        with pytest.raises(LLMError, match="invalid"):
            await _service_with_reply('{"budget_total_inr": "lots"}').extract_intent("x")

    async def test_structured_rejects_an_empty_reply(self) -> None:
        with pytest.raises(LLMError, match="no StyleIntent"):
            await _service_with_reply(None).extract_intent("x")


def _service_with_reply(arguments: str | None) -> LLMService:
    """An enabled service whose client replies with ``arguments`` as the message content (None: empty)."""
    settings = MagicMock()
    settings.vlm_api_key = "sk-test-key"
    settings.vlm_base_url = "https://openrouter.ai/api/v1"
    svc = LLMService(settings=settings)
    message = SimpleNamespace(content=arguments)
    svc._client = MagicMock()
    svc._client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)])
    )
    return svc
