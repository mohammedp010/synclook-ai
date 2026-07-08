"""Tests for StyleIntent schema, heuristic parsing, and IntentAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock

from backend.agents.base import AgentContext
from backend.agents.intent_agent import IntentAgent, heuristic_intent, intent_from_context
from backend.core.exceptions import LLMError
from backend.schemas.clothing import Style
from backend.schemas.intent import RecommendationIssue, StyleIntent


class TestStyleIntentNormalization:
    def test_negative_budget_dropped(self) -> None:
        intent = StyleIntent(budget_total_inr=-100).normalized()
        assert intent.budget_total_inr is None

    def test_lists_are_deduped_lowercased_capped(self) -> None:
        intent = StyleIntent(avoid_items=["  Blazer ", "blazer", "SKIRT"] + [f"item{i}" for i in range(20)])
        normalized = intent.normalized()
        assert normalized.avoid_items[:2] == ["blazer", "skirt"]
        assert len(normalized.avoid_items) <= 8

    def test_preferred_styles_capped_and_deduped(self) -> None:
        intent = StyleIntent(preferred_styles=[Style.FORMAL, Style.FORMAL, Style.CASUAL, Style.SPORTY, Style.BOHEMIAN])
        assert intent.normalized().preferred_styles == [Style.FORMAL, Style.CASUAL, Style.SPORTY]

    def test_is_empty(self) -> None:
        assert StyleIntent().is_empty
        assert not StyleIntent(occasion="wedding").is_empty


class TestHeuristicIntent:
    def test_budget_extraction(self) -> None:
        intent = heuristic_intent("Style this for a dinner under ₹5,000")
        assert intent.budget_total_inr == 5000.0
        assert intent.occasion == "dinner"

    def test_climate_and_occasion(self) -> None:
        intent = heuristic_intent("something for a rainy office day")
        assert intent.climate == "rainy"
        assert intent.occasion == "office"
        assert Style.SMART_CASUAL in intent.preferred_styles

    def test_explicit_style_mention_wins(self) -> None:
        intent = heuristic_intent("make this more streetwear for a party")
        assert intent.preferred_styles[0] == Style.STREETWEAR

    def test_no_shopping_phrase(self) -> None:
        intent = heuristic_intent("suggest outfits, no shopping links please")
        assert intent.wants_shopping is False

    def test_plain_text_yields_empty_intent(self) -> None:
        assert heuristic_intent("what do you think?").is_empty


class TestIntentAgent:
    async def test_no_text_sets_none(self) -> None:
        ctx = AgentContext(image_bytes=b"x")
        ctx = await IntentAgent(llm_service=None).run(ctx)
        assert ctx.metadata["intent"] is None
        assert intent_from_context(ctx) is None

    async def test_heuristic_fallback_without_llm(self) -> None:
        ctx = AgentContext(image_bytes=b"x")
        ctx.metadata["user_intent_text"] = "office look under 3000"
        ctx = await IntentAgent(llm_service=None).run(ctx)
        intent = intent_from_context(ctx)
        assert intent is not None
        assert intent.budget_total_inr == 3000.0
        assert ctx.metadata["intent_source"] == "heuristic"

    async def test_llm_path_used_when_enabled(self) -> None:
        llm = AsyncMock()
        llm.enabled = True
        llm.extract_intent = AsyncMock(return_value=StyleIntent(occasion="wedding", preferred_styles=[Style.FORMAL]))
        ctx = AgentContext(image_bytes=b"x")
        ctx.metadata["user_intent_text"] = "what should I wear to a wedding?"
        ctx = await IntentAgent(llm_service=llm).run(ctx)
        intent = intent_from_context(ctx)
        assert intent is not None
        assert intent.occasion == "wedding"
        assert ctx.metadata["intent_source"] == "llm"

    async def test_llm_failure_falls_back_to_heuristic(self) -> None:
        llm = AsyncMock()
        llm.enabled = True
        llm.extract_intent = AsyncMock(side_effect=LLMError("down"))
        ctx = AgentContext(image_bytes=b"x")
        ctx.metadata["user_intent_text"] = "gym outfit"
        ctx = await IntentAgent(llm_service=llm).run(ctx)
        intent = intent_from_context(ctx)
        assert intent is not None
        assert Style.SPORTY in intent.preferred_styles
        assert ctx.metadata["intent_source"] == "heuristic"


class TestRecommendationIssue:
    def test_fixable_codes(self) -> None:
        fixable = RecommendationIssue(recommendation_index=0, code="forbidden_item", detail="x", item_type="skirt")
        not_fixable = RecommendationIssue(recommendation_index=0, code="budget_exceeded", detail="x")
        assert fixable.fixable
        assert not not_fixable.fixable
