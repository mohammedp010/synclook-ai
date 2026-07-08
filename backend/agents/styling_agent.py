"""Styling Agent — rule-based color matching and style compatibility engine.

Delegates styling intelligence to ColorMatcherTool and StyleRuleEngineTool.
No LLM calls — DeepSeek is reserved for tone refinement of explanations only.
"""

from __future__ import annotations

from backend.agents.base import AgentContext, BaseAgent, StyleMatch
from backend.core.config import get_settings
from backend.core.exceptions import AgentError
from backend.core.logging import get_logger
from backend.services.fashion_knowledge import FashionKnowledgeService
from backend.tools.color_matcher import ColorMatcherTool
from backend.tools.style_rules import StyleRuleEngineTool

logger = get_logger(__name__)

# Re-export rule tables for backward compatibility
from backend.tools.color_matcher import COLOR_COMPLEMENTS  # noqa: E402, F401
from backend.tools.style_rules import (  # noqa: E402, F401
    ITEM_PAIRINGS,
    PATTERN_PAIRS,
    STYLE_COMPATIBILITY,
    normalize_shopping_intent,
)


class StylingAgent(BaseAgent):
    """Deterministic rule-based styling engine.

    Reads ``ctx.clothing_attributes`` (set by VisionAgent) and produces
    a list of ``StyleMatch`` objects describing complementary garments.

    Uses ``ColorMatcherTool`` and ``StyleRuleEngineTool`` for all
    rule look-ups and scoring.
    """

    name = "styling"

    def __init__(self, fashion_knowledge: FashionKnowledgeService | None = None) -> None:
        super().__init__()
        self.color_tool = ColorMatcherTool()
        self.style_tool = StyleRuleEngineTool()
        self._knowledge = fashion_knowledge or FashionKnowledgeService()
        self._settings = get_settings()

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        attrs = ctx.clothing_attributes
        if attrs is None:
            raise AgentError("StylingAgent requires clothing_attributes in context")

        matches: list[StyleMatch] = []
        shopping_intent = normalize_shopping_intent(ctx.shopping_intent or ctx.gender)

        paired_types = self.style_tool.get_paired_items(
            attrs.clothing_type,
            gender=shopping_intent,
        )
        knowledge_matches = self._knowledge.get_best_matches(
            attrs.clothing_type.value,
            style=attrs.style.value,
            gender=shopping_intent,
        )
        knowledge_types = self._knowledge.to_clothing_types(knowledge_matches)

        low_confidence = attrs.confidence < self._settings.vision_low_confidence_threshold
        if low_confidence:
            fallback_items = self.style_tool.get_safe_fallback_items(
                attrs.clothing_type,
                detected_style=attrs.style,
                gender=shopping_intent,
            )
            if knowledge_types:
                fallback_knowledge = [it for it in knowledge_types if it in fallback_items]
                if fallback_knowledge:
                    fallback_items = fallback_knowledge
            if fallback_items:
                paired_types = fallback_items
            ctx.metadata["low_confidence_detection"] = True
        else:
            ctx.metadata["low_confidence_detection"] = False
            if knowledge_types:
                allowed = set(paired_types)
                ranked = [it for it in knowledge_types if it in allowed]
                if ranked:
                    paired_types = ranked

        complement_colors = self.color_tool.get_complements(attrs.primary_color)
        compatible_styles = self.style_tool.get_compatible_styles(attrs.style)

        for item_type in paired_types:
            if self._knowledge.is_forbidden_pair(
                base_item=attrs.clothing_type.value,
                candidate_item=item_type.value,
                gender=shopping_intent,
            ):
                continue

            if not self.style_tool.is_item_allowed_for_style(attrs.style, item_type):
                continue

            score = self.style_tool.compute_match_score(
                attrs.style, attrs.style, attrs.pattern,
            )

            colors_for_item = [c.value for c in complement_colors[:4]]
            styles_for_item = [s.value for s in compatible_styles[:3]]

            # Boost/penalise based on user preferences from memory
            prefs = ctx.metadata.get("user_preferences")
            if prefs:
                for c in colors_for_item:
                    if c in prefs.get("liked_colors", []):
                        score = min(score + 0.05, 1.0)
                    if c in prefs.get("disliked_colors", []):
                        score = max(score - 0.1, 0.0)
                for s in styles_for_item:
                    if s in prefs.get("liked_styles", []):
                        score = min(score + 0.05, 1.0)
                    if s in prefs.get("disliked_styles", []):
                        score = max(score - 0.1, 0.0)

            matches.append(
                StyleMatch(
                    item_type=item_type.value,
                    recommended_colors=colors_for_item,
                    recommended_styles=styles_for_item,
                    match_score=round(score, 2),
                    rule_source="color_complement+style_compat+pattern",
                )
            )

        # Sort by score descending, keep top results
        matches.sort(key=lambda m: m.match_score, reverse=True)
        ctx.style_matches = matches

        logger.info(
            "styling_complete",
            num_matches=len(matches),
            top_item=matches[0].item_type if matches else None,
            low_confidence_detection=low_confidence,
        )

        return ctx
