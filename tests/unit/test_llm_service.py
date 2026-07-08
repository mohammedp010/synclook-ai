"""Unit tests for LLMService."""

from unittest.mock import MagicMock

import pytest

from backend.core.exceptions import LLMError
from backend.services.llm import LLMService


def _disabled_service() -> LLMService:
    settings = MagicMock()
    settings.deepseek_api_key = ""
    return LLMService(settings=settings)


class TestLLMService:
    """Tests for LLMService — no real API calls."""

    def test_disabled_without_api_key(self) -> None:
        assert _disabled_service().enabled is False

    def test_enabled_with_api_key(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = "sk-test-key"
        settings.deepseek_base_url = "https://api.deepseek.com"
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

    async def test_critique_raises_when_disabled(self) -> None:
        with pytest.raises(LLMError):
            await _disabled_service().critique_recommendations(
                detected="navy shirt",
                intent_summary="office party",
                outfits=[{"items": ["trousers"]}],
            )
