"""Unit tests for RecommendationAgent."""

import pytest
from unittest.mock import AsyncMock

from backend.agents.base import AgentContext, StyleMatch
from backend.agents.recommendation_agent import (
    MAX_ITEMS_PER_OUTFIT,
    MAX_OUTFITS,
    RecommendationAgent,
    _build_recommendation,
    _diversify_color,
)
from backend.core.exceptions import AgentError
from backend.schemas.api import Recommendation, RecommendationItem
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)
from backend.tools.style_rules import StyleRuleEngineTool


class TestBuildRecommendation:
    """Tests for the _build_recommendation helper."""

    def test_builds_recommendation_from_matches(self) -> None:
        matches = [
            StyleMatch("trousers", ["white", "grey"], ["smart_casual"], 0.9, "test"),
            StyleMatch("blazer", ["beige", "cream"], ["formal"], 0.85, "test"),
        ]
        rec = _build_recommendation(matches, "shirt", "navy", "smart_casual")
        assert isinstance(rec, Recommendation)
        assert len(rec.items) == 2
        assert rec.items[0].item_type == "trousers"
        assert rec.items[0].color == "white"

    def test_explanation_contains_detected_info(self) -> None:
        matches = [StyleMatch("jeans", ["black"], ["casual"], 0.8, "test")]
        rec = _build_recommendation(matches, "t-shirt", "red", "casual")
        assert "t-shirt" in rec.overall_explanation
        assert "red" in rec.overall_explanation
        assert "casual" in rec.overall_explanation

    def test_confidence_is_average_of_scores(self) -> None:
        matches = [
            StyleMatch("jeans", ["black"], ["casual"], 0.8, "test"),
            StyleMatch("jacket", ["grey"], ["casual"], 0.6, "test"),
        ]
        rec = _build_recommendation(matches, "shirt", "blue", "casual")
        assert rec.confidence == 0.7


class TestDiversifyColor:
    """Tests for the _diversify_color helper."""

    def test_rotates_colors(self) -> None:
        match = StyleMatch("jeans", ["white", "grey", "black"], ["casual"], 0.9, "test")
        diversified = _diversify_color(match, 1)
        assert diversified.recommended_colors == ["grey", "black", "white"]

    def test_applies_score_penalty(self) -> None:
        match = StyleMatch("jeans", ["white"], ["casual"], 1.0, "test")
        diversified = _diversify_color(match, 1)
        assert diversified.match_score < 1.0

    def test_variant_zero_keeps_original_order(self) -> None:
        match = StyleMatch("jeans", ["white", "grey"], ["casual"], 0.9, "test")
        diversified = _diversify_color(match, 0)
        assert diversified.recommended_colors == ["white", "grey"]


class TestRecommendationAgent:
    """Tests for RecommendationAgent with LLM disabled."""

    @pytest.fixture
    def agent(self) -> RecommendationAgent:
        return RecommendationAgent(llm_service=None)

    async def test_produces_recommendations(
        self, agent: RecommendationAgent, sample_context_with_matches: AgentContext
    ) -> None:
        result = await agent.run(sample_context_with_matches)
        assert len(result.recommendations) > 0
        assert len(result.recommendations) <= MAX_OUTFITS

    async def test_each_recommendation_has_items(
        self, agent: RecommendationAgent, sample_context_with_matches: AgentContext
    ) -> None:
        result = await agent.run(sample_context_with_matches)
        for rec in result.recommendations:
            assert isinstance(rec, Recommendation)
            assert len(rec.items) > 0
            assert len(rec.items) <= MAX_ITEMS_PER_OUTFIT

    async def test_items_have_reasons(
        self, agent: RecommendationAgent, sample_context_with_matches: AgentContext
    ) -> None:
        result = await agent.run(sample_context_with_matches)
        for rec in result.recommendations:
            for item in rec.items:
                assert item.reason
                assert len(item.reason) > 0

    async def test_different_outfits_have_different_colors(
        self, agent: RecommendationAgent, sample_context_with_matches: AgentContext
    ) -> None:
        result = await agent.run(sample_context_with_matches)
        if len(result.recommendations) >= 2:
            colors_0 = {it.color for it in result.recommendations[0].items}
            colors_1 = {it.color for it in result.recommendations[1].items}
            # At least one different color due to diversification
            assert colors_0 != colors_1 or len(result.recommendations[0].items) == 0

    async def test_raises_without_style_matches(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.SHIRT,
            primary_color=Color.NAVY,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.8,
        )
        with pytest.raises(AgentError, match="style_matches"):
            await agent.run(ctx)

    async def test_raises_without_attributes(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake")
        ctx.style_matches = [
            StyleMatch("jeans", ["black"], ["casual"], 0.8, "test"),
        ]
        with pytest.raises(AgentError, match="clothing_attributes"):
            await agent.run(ctx)

    async def test_llm_enrichment_skipped_when_disabled(
        self, agent: RecommendationAgent, sample_context_with_matches: AgentContext
    ) -> None:
        result = await agent.run(sample_context_with_matches)
        # Template text should contain "Based on your"
        for rec in result.recommendations:
            assert "Based on your" in rec.overall_explanation

    async def test_llm_enrichment_called_when_enabled(
        self, sample_context_with_matches: AgentContext
    ) -> None:
        mock_llm = AsyncMock()
        mock_llm.enabled = True
        mock_llm.generate_outfit_explanation = AsyncMock(return_value="LLM-generated explanation")
        mock_llm.generate_item_reason = AsyncMock(return_value="LLM-generated reason")

        agent = RecommendationAgent(llm_service=mock_llm)
        result = await agent.run(sample_context_with_matches)

        mock_llm.generate_outfit_explanation.assert_called()
        assert result.recommendations[0].overall_explanation == "LLM-generated explanation"

    async def test_llm_failure_falls_back_to_template(
        self, sample_context_with_matches: AgentContext
    ) -> None:
        from backend.core.exceptions import LLMError

        mock_llm = AsyncMock()
        mock_llm.enabled = True
        mock_llm.generate_outfit_explanation = AsyncMock(side_effect=LLMError("API down"))

        agent = RecommendationAgent(llm_service=mock_llm)
        result = await agent.run(sample_context_with_matches)

        # Should fall back to templates
        assert "Based on your" in result.recommendations[0].overall_explanation

    async def test_filters_invalid_items_for_gender(self) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.75,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white"], ["streetwear"], 0.9, "test"),
            StyleMatch("blouse", ["white"], ["streetwear"], 0.88, "test"),
        ]

        agent = RecommendationAgent(llm_service=None)
        result = await agent.run(ctx)

        suggested_items = {
            item.item_type
            for rec in result.recommendations
            for item in rec.items
        }
        assert "blouse" not in suggested_items
        assert "shirt" in suggested_items

    async def test_filters_invalid_items_for_menswear_intent(self) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="unisex", shopping_intent="menswear")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.BOHEMIAN,
            confidence=0.75,
        )
        ctx.style_matches = [
            StyleMatch("blouse", ["white"], ["bohemian"], 0.88, "test"),
            StyleMatch("shirt", ["white"], ["bohemian"], 0.86, "test"),
        ]

        agent = RecommendationAgent(llm_service=None)
        result = await agent.run(ctx)

        suggested_items = {
            item.item_type
            for rec in result.recommendations
            for item in rec.items
        }
        assert "blouse" not in suggested_items
        assert "shirt" in suggested_items

    async def test_all_intent_does_not_apply_menswear_exclusions(self) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male", shopping_intent="all")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.BOHEMIAN,
            confidence=0.75,
        )
        ctx.style_matches = [
            StyleMatch("blouse", ["white"], ["bohemian"], 0.88, "test"),
        ]

        agent = RecommendationAgent(llm_service=None)
        result = await agent.run(ctx)

        suggested_items = {
            item.item_type
            for rec in result.recommendations
            for item in rec.items
        }
        assert "blouse" in suggested_items

    async def test_bottomwear_look_has_single_topwear(self) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.81,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white", "grey"], ["casual"], 0.9, "test"),
            StyleMatch("hoodie", ["white", "grey"], ["streetwear"], 0.88, "test"),
            StyleMatch("blazer", ["grey"], ["formal"], 0.7, "test"),
        ]

        agent = RecommendationAgent(llm_service=None)
        result = await agent.run(ctx)

        style_tool = StyleRuleEngineTool()
        for rec in result.recommendations:
            topwear_count = sum(
                1
                for item in rec.items
                if style_tool.get_item_category(item.item_type) == "topwear"
            )
            assert topwear_count == 1

    async def test_streetwear_bottomwear_skips_outerwear(self) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.8,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white", "grey"], ["streetwear"], 0.9, "test"),
            StyleMatch("blazer", ["grey"], ["formal"], 0.75, "test"),
        ]

        agent = RecommendationAgent(llm_service=None)
        result = await agent.run(ctx)

        outerwear_types = {"blazer", "jacket", "coat"}
        suggested = {
            item.item_type
            for rec in result.recommendations
            for item in rec.items
        }
        assert suggested.isdisjoint(outerwear_types)

    async def test_style_tags_are_deduplicated(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.85,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white"], ["streetwear"], 0.9, "test"),
            StyleMatch("hoodie", ["grey"], ["streetwear"], 0.88, "test"),
        ]

        result = await agent.run(ctx)
        tags = result.recommendations[0].style_tags
        assert tags == ["streetwear"]

    async def test_bottomwear_outfit_respects_structured_item_cap(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.85,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white"], ["casual"], 0.9, "test"),
            StyleMatch("jacket", ["grey"], ["casual"], 0.85, "test"),
            StyleMatch("hoodie", ["red"], ["casual"], 0.84, "test"),
            StyleMatch("shoes", ["black"], ["casual"], 0.82, "test"),
            StyleMatch("accessory", ["brown"], ["casual"], 0.8, "test"),
        ]

        result = await agent.run(ctx)
        for rec in result.recommendations:
            assert len(rec.items) <= MAX_ITEMS_PER_OUTFIT

    async def test_bottomwear_look_can_include_footwear(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.85,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white"], ["casual"], 0.9, "test"),
            StyleMatch("shoes", ["black"], ["casual"], 0.82, "test"),
            StyleMatch("accessory", ["brown"], ["casual"], 0.8, "test"),
        ]

        result = await agent.run(ctx)
        first_items = {item.item_type for item in result.recommendations[0].items}
        assert "shirt" in first_items
        assert "shoes" in first_items

    async def test_topwear_look_can_include_footwear(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="unisex")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.SHIRT,
            primary_color=Color.NAVY,
            pattern=Pattern.SOLID,
            style=Style.SMART_CASUAL,
            confidence=0.88,
        )
        ctx.style_matches = [
            StyleMatch("trousers", ["grey"], ["smart_casual"], 0.9, "test"),
            StyleMatch("shoes", ["brown"], ["smart_casual"], 0.84, "test"),
            StyleMatch("accessory", ["black"], ["smart_casual"], 0.8, "test"),
        ]

        result = await agent.run(ctx)
        first_items = {item.item_type for item in result.recommendations[0].items}
        assert "trousers" in first_items
        assert "shoes" in first_items

    async def test_dress_generates_recommendations(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="female")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.DRESS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.9,
        )
        ctx.style_matches = [
            StyleMatch("jacket", ["black", "beige"], ["casual"], 0.85, "test"),
            StyleMatch("shoes", ["black"], ["casual"], 0.82, "test"),
            StyleMatch("accessory", ["beige"], ["casual"], 0.8, "test"),
        ]

        result = await agent.run(ctx)
        assert len(result.recommendations) > 0
        assert any(item.item_type == "jacket" for item in result.recommendations[0].items)

    async def test_suit_generates_recommendations(self, agent: RecommendationAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.SUIT,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.FORMAL,
            confidence=0.92,
        )
        ctx.style_matches = [
            StyleMatch("shirt", ["white", "cream"], ["formal"], 0.9, "test"),
            StyleMatch("coat", ["black"], ["formal"], 0.8, "test"),
            StyleMatch("shoes", ["black"], ["formal"], 0.82, "test"),
            StyleMatch("accessory", ["black"], ["formal"], 0.78, "test"),
        ]

        result = await agent.run(ctx)
        assert len(result.recommendations) > 0
        suggested = {item.item_type for rec in result.recommendations for item in rec.items}
        assert "shirt" in suggested
