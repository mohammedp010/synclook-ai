"""Recommendation Agent — converts StyleMatches into user-facing Recommendations.

Uses rule-based reasoning to build outfit suggestions.
If an LLMService is provided, explanations are tone-refined via DeepSeek.
Falls back to template strings if LLM is unavailable.
"""

from __future__ import annotations

from uuid import uuid4

from backend.agents.base import AgentContext, BaseAgent, StyleMatch
from backend.core.exceptions import AgentError, LLMError
from backend.core.logging import get_logger
from backend.schemas.api import Recommendation, RecommendationItem
from backend.services.fashion_knowledge import FashionKnowledgeService
from backend.services.llm import LLMService
from backend.tools.style_rules import StyleRuleEngineTool, normalize_shopping_intent

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  Explanation templates (fallback when LLM is unavailable)
# ──────────────────────────────────────────────────────────────────────

_OUTFIT_TEMPLATE = (
    "Based on your {detected_type} in {detected_color}, we suggest pairing it with "
    "complementary pieces that maintain a {detected_style} aesthetic. "
    "The recommended colors ({colors}) create a cohesive look, "
    "and the mix of items balances proportions and silhouette."
)

_ITEM_REASON_TEMPLATE = (
    "{color} {item_type} — pairs well with your {detected_color} {detected_type} for a {style} look."
)

# Maximum recommendations per request.
MAX_OUTFITS = 3
MAX_ITEMS_PER_OUTFIT = 4
ALT_RANK_PENALTY_STEP = 0.03
ALT_RANK_PENALTY_MAX = 0.15


# ──────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────


def _build_recommendation(
    matches: list[StyleMatch],
    detected_type: str,
    detected_color: str,
    detected_style: str,
) -> Recommendation:
    """Turn a slice of StyleMatches into one Recommendation."""
    items: list[RecommendationItem] = []
    first_color = ""

    for m in matches:
        color = m.recommended_colors[0] if m.recommended_colors else "neutral"
        style = m.recommended_styles[0] if m.recommended_styles else detected_style
        if not first_color:
            first_color = color

        items.append(
            RecommendationItem(
                item_type=m.item_type,
                color=color,
                style=style,
                reason=_ITEM_REASON_TEMPLATE.format(
                    color=color,
                    item_type=m.item_type,
                    detected_color=detected_color,
                    detected_type=detected_type,
                    style=style,
                ),
            )
        )

    avg_score = sum(m.match_score for m in matches) / len(matches) if matches else 0.5
    all_colors = ", ".join(dict.fromkeys(m.recommended_colors[0] for m in matches if m.recommended_colors))

    style_tags = [detected_style] + [m.recommended_styles[0] for m in matches if m.recommended_styles]
    deduped_style_tags = list(dict.fromkeys(style_tags))

    return Recommendation(
        id=uuid4(),
        items=items,
        overall_explanation=_OUTFIT_TEMPLATE.format(
            detected_type=detected_type,
            detected_color=detected_color,
            detected_style=detected_style,
            colors=all_colors or "complementary tones",
        ),
        style_tags=deduped_style_tags,
        confidence=round(avg_score, 2),
    )


def _diversify_color(match: StyleMatch, variant_index: int) -> StyleMatch:
    """Return a copy of a match with a different color alternative to add variety."""
    colors = match.recommended_colors
    if variant_index < len(colors):
        rotated = colors[variant_index:] + colors[:variant_index]
    else:
        rotated = colors
    return StyleMatch(
        item_type=match.item_type,
        recommended_colors=rotated,
        recommended_styles=match.recommended_styles,
        match_score=match.match_score * 0.95,  # slight penalty for non-primary
        rule_source=match.rule_source,
    )


# ──────────────────────────────────────────────────────────────────────
#  Agent
# ──────────────────────────────────────────────────────────────────────


class RecommendationAgent(BaseAgent):
    """Converts StyleMatches into user-facing Recommendation objects.

    Generates up to ``MAX_OUTFITS`` outfit suggestions, each containing
    up to ``MAX_ITEMS_PER_OUTFIT`` items.  Different outfits use
    different color variants for diversity.

    If an ``LLMService`` is provided and enabled, rule-generated explanations
    are tone-refined via DeepSeek without changing outfit facts.  Otherwise
    template strings are used.
    """

    name = "recommendation"

    def __init__(
        self,
        llm_service: LLMService | None = None,
        fashion_knowledge: FashionKnowledgeService | None = None,
    ) -> None:
        super().__init__()
        self._llm = llm_service
        self._style_tool = StyleRuleEngineTool()
        self._knowledge = fashion_knowledge or FashionKnowledgeService()

    def _style_supports_outerwear(self, detected_style: str) -> bool:
        """Keep layering controlled to avoid irrelevant outerwear spam."""
        return detected_style in {"formal", "smart_casual", "casual", "minimalist"}

    def _pick_category_match(
        self,
        matches: list[StyleMatch],
        *,
        category: str,
        variant_index: int,
        used_item_types: set[str],
    ) -> StyleMatch | None:
        candidates = [
            m
            for m in matches
            if self._style_tool.get_item_category(m.item_type) == category and m.item_type not in used_item_types
        ]
        if not candidates:
            return None
        chosen = candidates[variant_index % len(candidates)]
        return _diversify_color(chosen, variant_index)

    def _apply_rank_penalty(
        self,
        matches: list[StyleMatch],
        *,
        rank_map: dict[str, int],
    ) -> list[StyleMatch]:
        """Apply a small score penalty to low-priority alternate items.

        Keeps ranking deterministic while discouraging weak alternates from
        dominating across multiple looks.
        """
        adjusted: list[StyleMatch] = []
        default_rank = len(rank_map) + 3

        for m in matches:
            item_key = FashionKnowledgeService.normalize_item_name(m.item_type)
            rank_idx = rank_map.get(item_key, default_rank)
            penalty = min(rank_idx * ALT_RANK_PENALTY_STEP, ALT_RANK_PENALTY_MAX)
            adjusted.append(
                StyleMatch(
                    item_type=m.item_type,
                    recommended_colors=m.recommended_colors,
                    recommended_styles=m.recommended_styles,
                    match_score=round(max(m.match_score - penalty, 0.0), 2),
                    rule_source=m.rule_source,
                )
            )
        return adjusted

    async def _enrich_recommendation(
        self,
        rec: Recommendation,
        detected_type: str,
        detected_color: str,
        detected_style: str,
    ) -> Recommendation:
        """Tone-refine deterministic explanations without changing outfit facts."""
        if self._llm is None or not self._llm.enabled:
            return rec

        try:
            # Refine overall explanation wording only.
            overall = await self._llm.generate_outfit_explanation(
                detected_type=detected_type,
                detected_color=detected_color,
                detected_style=detected_style,
                rule_text=rec.overall_explanation,
            )
            rec.overall_explanation = overall

            # Refine individual item reason wording only.
            for item in rec.items:
                reason = await self._llm.generate_item_reason(
                    detected_type=detected_type,
                    detected_color=detected_color,
                    detected_style=detected_style,
                    rule_text=item.reason,
                )
                item.reason = reason

        except LLMError as exc:
            # Fallback to templates — already set during _build_recommendation
            logger.warning("llm_enrichment_failed", error=str(exc))

        return rec

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        if not ctx.style_matches:
            raise AgentError("RecommendationAgent requires style_matches in context")
        attrs = ctx.clothing_attributes
        if attrs is None:
            raise AgentError("RecommendationAgent requires clothing_attributes in context")

        detected_type = attrs.clothing_type.value
        detected_color = attrs.primary_color.value
        detected_style = attrs.style.value
        shopping_intent = normalize_shopping_intent(ctx.shopping_intent or ctx.gender)

        valid_matches = [
            m
            for m in ctx.style_matches
            if self._style_tool.is_item_allowed_for_gender(m.item_type, shopping_intent)
            and self._style_tool.is_item_allowed_for_style(attrs.style, m.item_type)
            and not self._knowledge.is_forbidden_pair(
                base_item=detected_type,
                candidate_item=m.item_type,
                gender=shopping_intent,
            )
        ]

        preferred_items = self._knowledge.get_best_matches(
            detected_type,
            style=detected_style,
            gender=shopping_intent,
        )
        if preferred_items:
            rank = {name: idx for idx, name in enumerate(preferred_items)}
            unknown_rank = len(rank) + 100
            valid_matches.sort(
                key=lambda m: (
                    rank.get(FashionKnowledgeService.normalize_item_name(m.item_type), unknown_rank),
                    -m.match_score,
                    m.item_type,
                )
            )
            valid_matches = self._apply_rank_penalty(valid_matches, rank_map=rank)

        outfit_structure = self._style_tool.get_outfit_structure(detected_type)

        recommendations: list[Recommendation] = []

        for outfit_idx in range(MAX_OUTFITS):
            outfit_matches: list[StyleMatch] = []
            used_item_types: set[str] = set()

            # Required categories must be present (e.g. bottomwear -> one topwear).
            required_ok = True
            for req_category in outfit_structure.get("required", []):
                match = self._pick_category_match(
                    valid_matches,
                    category=req_category,
                    variant_index=outfit_idx,
                    used_item_types=used_item_types,
                )
                if match is None:
                    required_ok = False
                    break
                outfit_matches.append(match)
                used_item_types.add(match.item_type)

            # Hard contract for bottomwear inputs: exactly one topwear in extras.
            if self._style_tool.get_item_category(detected_type) == "bottomwear":
                topwear_matches = [
                    m for m in outfit_matches if self._style_tool.get_item_category(m.item_type) == "topwear"
                ]
                if len(topwear_matches) != 1:
                    continue

            if not required_ok:
                continue

            # Optional categories are capped and style-gated.
            for opt_category in outfit_structure.get("optional", []):
                if len(outfit_matches) >= MAX_ITEMS_PER_OUTFIT:
                    break
                if opt_category == "outerwear" and not self._style_supports_outerwear(detected_style):
                    continue
                match = self._pick_category_match(
                    valid_matches,
                    category=opt_category,
                    variant_index=outfit_idx,
                    used_item_types=used_item_types,
                )
                if match is None:
                    continue
                outfit_matches.append(match)
                used_item_types.add(match.item_type)

            if not outfit_matches:
                break

            rec = _build_recommendation(
                outfit_matches,
                detected_type=detected_type,
                detected_color=detected_color,
                detected_style=detected_style,
            )

            # Tone-refine with LLM if available.
            rec = await self._enrich_recommendation(
                rec,
                detected_type,
                detected_color,
                detected_style,
            )

            recommendations.append(rec)

        ctx.recommendations = recommendations

        logger.info(
            "recommendations_complete",
            num_outfits=len(recommendations),
            total_items=sum(len(r.items) for r in recommendations),
            llm_enabled=self._llm is not None and self._llm.enabled,
        )

        return ctx
