"""Unit tests for StylingAgent."""

import pytest

from backend.agents.base import AgentContext, StyleMatch
from backend.agents.styling_agent import StylingAgent
from backend.core.exceptions import AgentError
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)
from backend.tools.color_matcher import COLOR_COMPLEMENTS
from backend.tools.style_rules import ITEM_PAIRINGS


class TestStylingAgent:
    """Tests for StylingAgent — deterministic rule-based styling."""

    @pytest.fixture
    def agent(self) -> StylingAgent:
        return StylingAgent()

    async def test_produces_style_matches(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        result = await agent.run(sample_context)
        assert len(result.style_matches) > 0
        assert all(isinstance(m, StyleMatch) for m in result.style_matches)

    async def test_match_items_come_from_pairing_table(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        result = await agent.run(sample_context)
        attrs = sample_context.clothing_attributes
        expected_types = [ct.value for ct in ITEM_PAIRINGS[attrs.clothing_type]]
        for match in result.style_matches:
            assert match.item_type in expected_types

    async def test_match_colors_come_from_complement_table(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        result = await agent.run(sample_context)
        attrs = sample_context.clothing_attributes
        expected_colors = [c.value for c in COLOR_COMPLEMENTS[attrs.primary_color]]
        for match in result.style_matches:
            for color in match.recommended_colors:
                assert color in expected_colors

    async def test_matches_sorted_by_score_descending(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        result = await agent.run(sample_context)
        scores = [m.match_score for m in result.style_matches]
        assert scores == sorted(scores, reverse=True)

    async def test_scores_in_valid_range(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        result = await agent.run(sample_context)
        for match in result.style_matches:
            assert 0.0 <= match.match_score <= 1.0

    async def test_raises_without_attributes(self, agent: StylingAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake")
        with pytest.raises(AgentError, match="clothing_attributes"):
            await agent.run(ctx)

    async def test_user_preference_boost(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        """Liked colors should result in a score boost."""
        # Run without preferences
        ctx_no_prefs = AgentContext(
            image_bytes=sample_context.image_bytes,
            user_id="u1",
        )
        ctx_no_prefs.clothing_attributes = sample_context.clothing_attributes
        result_no = await agent.run(ctx_no_prefs)
        base_score = result_no.style_matches[0].match_score

        # Run with liked color matching the first complement
        first_complement = COLOR_COMPLEMENTS[sample_context.clothing_attributes.primary_color][0].value
        ctx_prefs = AgentContext(
            image_bytes=sample_context.image_bytes,
            user_id="u2",
        )
        ctx_prefs.clothing_attributes = sample_context.clothing_attributes
        ctx_prefs.metadata["user_preferences"] = {
            "liked_colors": [first_complement],
            "disliked_colors": [],
            "liked_styles": [],
            "disliked_styles": [],
        }
        agent2 = StylingAgent()
        result_prefs = await agent2.run(ctx_prefs)
        boosted_score = result_prefs.style_matches[0].match_score

        assert boosted_score >= base_score

    async def test_user_preference_penalty(self, agent: StylingAgent, sample_context: AgentContext) -> None:
        """Disliked colors should result in a score penalty."""
        first_complement = COLOR_COMPLEMENTS[sample_context.clothing_attributes.primary_color][0].value
        ctx = AgentContext(
            image_bytes=sample_context.image_bytes,
            user_id="u3",
        )
        ctx.clothing_attributes = sample_context.clothing_attributes
        ctx.metadata["user_preferences"] = {
            "liked_colors": [],
            "disliked_colors": [first_complement],
            "liked_styles": [],
            "disliked_styles": [],
        }
        agent2 = StylingAgent()
        result = await agent2.run(ctx)

        # Run without preferences for comparison
        ctx_base = AgentContext(image_bytes=b"fake", user_id="u4")
        ctx_base.clothing_attributes = sample_context.clothing_attributes
        agent3 = StylingAgent()
        result_base = await agent3.run(ctx_base)

        assert result.style_matches[0].match_score <= result_base.style_matches[0].match_score

    async def test_various_clothing_types(self, agent: StylingAgent) -> None:
        """Agent should work for all clothing types."""
        for ct in ClothingType:
            ctx = AgentContext(image_bytes=b"fake")
            ctx.clothing_attributes = ClothingAttributes(
                clothing_type=ct,
                primary_color=Color.BLACK,
                pattern=Pattern.SOLID,
                style=Style.CASUAL,
                confidence=0.8,
            )
            result = await agent.run(ctx)
            assert len(result.style_matches) > 0

    async def test_gender_filter_excludes_blouse_for_male_trousers(self, agent: StylingAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.8,
        )
        result = await agent.run(ctx)
        suggested = {m.item_type for m in result.style_matches}
        assert "blouse" not in suggested

    async def test_streetwear_filter_excludes_blazer_for_trousers(self, agent: StylingAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.8,
        )
        result = await agent.run(ctx)
        suggested = {m.item_type for m in result.style_matches}
        assert "blazer" not in suggested

    async def test_low_confidence_uses_safe_fallback(self, agent: StylingAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType.TROUSERS,
            primary_color=Color.BLACK,
            pattern=Pattern.SOLID,
            style=Style.STREETWEAR,
            confidence=0.2,
        )
        result = await agent.run(ctx)

        assert result.metadata["low_confidence_detection"] is True
        suggested = {m.item_type for m in result.style_matches}
        assert suggested.issubset({"shirt", "t-shirt", "hoodie", "sweater"})
