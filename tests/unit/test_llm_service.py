"""Unit tests for LLMService."""

from unittest.mock import MagicMock

import pytest

from backend.core.exceptions import LLMError
from backend.services.llm import LLMService


class TestLLMService:
    """Tests for LLMService — no real API calls."""

    def test_disabled_without_api_key(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = ""
        svc = LLMService(settings=settings)
        assert svc.enabled is False

    def test_enabled_with_api_key(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = "sk-test-key"
        settings.deepseek_base_url = "https://api.deepseek.com"
        svc = LLMService(settings=settings)
        assert svc.enabled is True

    async def test_chat_raises_when_disabled(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = ""
        svc = LLMService(settings=settings)
        with pytest.raises(LLMError, match="disabled"):
            await svc._chat("test prompt")

    async def test_generate_outfit_explanation_when_disabled(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = ""
        svc = LLMService(settings=settings)
        with pytest.raises(LLMError):
            await svc.generate_outfit_explanation(
                detected_type="shirt",
                detected_color="navy",
                detected_style="casual",
                rule_text="Navy shirt pairs with black jeans for a casual contrast.",
            )

    async def test_generate_item_reason_when_disabled(self) -> None:
        settings = MagicMock()
        settings.deepseek_api_key = ""
        svc = LLMService(settings=settings)
        with pytest.raises(LLMError):
            await svc.generate_item_reason(
                detected_type="shirt",
                detected_color="navy",
                detected_style="casual",
                rule_text="Black jeans balance the navy shirt with clean casual contrast.",
            )
