"""Styling Agent — rule-based color matching and style compatibility engine.

Delegates styling intelligence to ColorMatcherTool and StyleRuleEngineTool.
Deterministic by design: the only LLM influence is the validated StyleIntent
produced upstream (effective style, avoid list), never free-form output.
"""

from __future__ import annotations

from backend.agents.base import AgentContext, BaseAgent, StyleMatch
from backend.agents.intent_agent import intent_from_context
from backend.core.config import get_settings
from backend.core.exceptions import AgentError
from backend.core.logging import get_logger
from backend.schemas.clothing import ClothingAttributes, ClothingType, Style
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

    def _build_matches(
        self,
        paired_types: list[ClothingType],
        attrs: ClothingAttributes,
        ctx: AgentContext,
        shopping_intent: str,
        effective_style: Style,
        *,
        avoid_items: set[str] | None = None,
        relax_style: bool = False,
        rule_source: str = "color_complement+style_compat+pattern",
    ) -> list[StyleMatch]:
        """Score candidate item types into StyleMatch objects.

        ``effective_style`` is the style constraints are evaluated against —
        the user's requested style when an intent provides one, otherwise the
        detected style. ``relax_style=True`` skips the style-policy filter —
        used for safe fallbacks, where the candidate list is already
        conservative and coverage matters more than strict style adherence.
        """
        matches: list[StyleMatch] = []
        avoid = avoid_items or set()
        complement_colors = self.color_tool.get_complements(attrs.primary_color)
        compatible_styles = self.style_tool.get_compatible_styles(effective_style)

        for item_type in paired_types:
            if item_type.value in avoid:
                continue

            if self._knowledge.is_forbidden_pair(
                base_item=attrs.clothing_type.value,
                candidate_item=item_type.value,
                gender=shopping_intent,
            ):
                continue

            if not relax_style and not self.style_tool.is_item_allowed_for_style(effective_style, item_type):
                continue

            score = self.style_tool.compute_match_score(
                effective_style,
                effective_style,
                attrs.pattern,
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
                    rule_source=rule_source,
                )
            )

        matches.sort(key=lambda m: m.match_score, reverse=True)
        return matches

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        attrs = ctx.clothing_attributes
        if attrs is None:
            raise AgentError("StylingAgent requires clothing_attributes in context")

        shopping_intent = normalize_shopping_intent(ctx.shopping_intent or ctx.gender)

        # Intent constraints (LLM-proposed, deterministically validated):
        # the requested style becomes the effective style; avoid-listed items
        # are excluded outright.
        intent = intent_from_context(ctx)
        effective_style = attrs.style
        avoid_items: set[str] = set()
        if intent is not None:
            if intent.preferred_styles:
                effective_style = intent.preferred_styles[0]
            avoid_items = set(intent.avoid_items)
        ctx.metadata["effective_style"] = effective_style.value

        low_confidence = attrs.confidence < self._settings.vision_low_confidence_threshold
        ctx.metadata["low_confidence_detection"] = low_confidence

        if low_confidence:
            # Conservative structure-covering fallback; the style filter is
            # relaxed because get_safe_fallback_items already applied it with
            # required-category coverage taking precedence.
            paired_types = self.style_tool.get_safe_fallback_items(
                attrs.clothing_type,
                detected_style=effective_style,
                gender=shopping_intent,
            )
            matches = self._build_matches(
                paired_types,
                attrs,
                ctx,
                shopping_intent,
                effective_style,
                avoid_items=avoid_items,
                relax_style=True,
                rule_source="safe_fallback",
            )
        else:
            paired_types = self.style_tool.get_paired_items(
                attrs.clothing_type,
                gender=shopping_intent,
            )
            knowledge_matches = self._knowledge.get_best_matches(
                attrs.clothing_type.value,
                style=effective_style.value,
                gender=shopping_intent,
            )
            knowledge_types = self._knowledge.to_clothing_types(knowledge_matches)
            if knowledge_types:
                allowed = set(paired_types)
                ranked = [it for it in knowledge_types if it in allowed]
                if ranked:
                    paired_types = ranked
            matches = self._build_matches(
                paired_types, attrs, ctx, shopping_intent, effective_style, avoid_items=avoid_items
            )

        # Style-policy dead zone (e.g. sporty blazer keeps only shoes/accessory):
        # if the matches cannot cover the outfit structure's required categories,
        # extend them with conservative structure-covering items instead of
        # letting the recommendation stage produce nothing.
        structure = self.style_tool.get_outfit_structure(attrs.clothing_type)
        covered = {self.style_tool.get_item_category(m.item_type) for m in matches}
        missing = [category for category in structure.get("required", []) if category not in covered]
        if missing or not matches:
            safe_items = self.style_tool.get_safe_fallback_items(
                attrs.clothing_type,
                detected_style=effective_style,
                gender=shopping_intent,
            )
            existing_types = {m.item_type for m in matches}
            gap_fillers = [
                item
                for item in safe_items
                if item.value not in existing_types
                and (not matches or self.style_tool.get_item_category(item) in missing)
            ]
            matches = matches + self._build_matches(
                gap_fillers,
                attrs,
                ctx,
                shopping_intent,
                effective_style,
                avoid_items=avoid_items,
                relax_style=True,
                rule_source="safe_fallback",
            )
            matches.sort(key=lambda m: m.match_score, reverse=True)
            ctx.metadata["style_dead_zone_fallback"] = True
            logger.warning(
                "styling_dead_zone_fallback",
                clothing_type=attrs.clothing_type.value,
                style=attrs.style.value,
                missing_categories=missing,
                num_matches=len(matches),
            )

        ctx.style_matches = matches

        logger.info(
            "styling_complete",
            num_matches=len(matches),
            top_item=matches[0].item_type if matches else None,
            low_confidence_detection=low_confidence,
        )

        return ctx
