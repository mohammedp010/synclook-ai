"""Verifier Agent — final quality gate before recommendations reach the user.

Deterministic checks always run (outfit completeness, forbidden items,
duplicates, budget, unsupported explanation claims). When an LLMService is
available, a structured critic pass adds subtler findings (occasion
mismatch). Issues are recorded in ``ctx.metadata['verifier_issues']``; the
graph decides whether fixable issues warrant one corrective rebuild.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.base import AgentContext, BaseAgent
from backend.agents.intent_agent import intent_from_context
from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.schemas.api import Recommendation
from backend.schemas.clothing import ClothingType
from backend.schemas.intent import RecommendationIssue, StyleIntent
from backend.services.llm import LLMService
from backend.tools.style_rules import (
    CLOTHING_TYPE_CATEGORIES,
    StyleRuleEngineTool,
    normalize_shopping_intent,
)

logger = get_logger(__name__)

_PRICE_DIGITS_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _parse_price(price: str) -> float | None:
    """Extract a numeric amount from a store price string like '₹1,299'."""
    match = _PRICE_DIGITS_RE.search(price or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


class VerifierAgent(BaseAgent):
    """Checks assembled recommendations against policy, structure, and intent."""

    name = "verifier"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        super().__init__()
        self._llm = llm_service
        self._style_tool = StyleRuleEngineTool()

    # ── Deterministic checks ─────────────────────────────────────────

    def _check_structure(self, idx: int, rec: Recommendation, base_type: ClothingType) -> list[RecommendationIssue]:
        structure = self._style_tool.get_outfit_structure(base_type)
        required = set(structure.get("required", []))
        covered = {CLOTHING_TYPE_CATEGORIES.get(base_type, "topwear")}
        for item in rec.items:
            covered.add(self._style_tool.get_item_category(item.item_type))
        missing = required - covered
        if missing:
            return [
                RecommendationIssue(
                    recommendation_index=idx,
                    code="incomplete_outfit",
                    detail=f"Missing required categories: {', '.join(sorted(missing))}",
                )
            ]
        return []

    def _check_items(
        self,
        idx: int,
        rec: Recommendation,
        shopping_intent: str,
        avoid_items: set[str],
    ) -> list[RecommendationIssue]:
        issues: list[RecommendationIssue] = []
        seen: set[str] = set()
        for item in rec.items:
            item_type = item.item_type.strip().lower()
            if item_type in seen:
                issues.append(
                    RecommendationIssue(
                        recommendation_index=idx,
                        code="duplicate_item",
                        detail=f"Duplicate item type '{item_type}' in one look",
                        item_type=item_type,
                    )
                )
            seen.add(item_type)

            if item_type in avoid_items or not self._style_tool.is_item_allowed_for_gender(item_type, shopping_intent):
                issues.append(
                    RecommendationIssue(
                        recommendation_index=idx,
                        code="forbidden_item",
                        detail=f"'{item_type}' violates the avoid list or shopping-intent policy",
                        item_type=item_type,
                    )
                )
        return issues

    def _check_budget(self, idx: int, rec: Recommendation, budget: float | None) -> list[RecommendationIssue]:
        if budget is None:
            return []
        total = 0.0
        priced_items = 0
        for item in rec.items:
            if item.owned or not item.products:
                continue
            prices = [p for p in (_parse_price(prod.price) for prod in item.products) if p is not None]
            if prices:
                total += min(prices)
                priced_items += 1
        if priced_items and total > budget:
            return [
                RecommendationIssue(
                    recommendation_index=idx,
                    code="budget_exceeded",
                    detail=f"Cheapest product combination ≈₹{total:,.0f} exceeds budget ₹{budget:,.0f}",
                )
            ]
        return []

    def _check_explanation_claims(
        self, idx: int, rec: Recommendation, base_type: ClothingType
    ) -> list[RecommendationIssue]:
        """Flag explanations that mention garment types not in the look."""
        text = rec.overall_explanation.lower()
        allowed = {base_type.value} | {item.item_type.strip().lower() for item in rec.items}

        # Mask longer type names first so 'shirt' doesn't fire inside 't-shirt'.
        for ct in sorted(ClothingType, key=lambda c: -len(c.value)):
            value = ct.value
            if ct == ClothingType.OTHER:
                continue
            pattern = re.compile(rf"(?<![\w-]){re.escape(value)}(?![\w-])")
            if pattern.search(text):
                if value not in allowed:
                    return [
                        RecommendationIssue(
                            recommendation_index=idx,
                            code="unsupported_claim",
                            detail=f"Explanation mentions '{value}' which is not part of the outfit",
                            item_type=value,
                        )
                    ]
                text = pattern.sub(" ", text)
        return []

    # ── Optional LLM critique ────────────────────────────────────────

    async def _llm_critique(
        self,
        recommendations: list[Recommendation],
        base_desc: str,
        intent: StyleIntent | None,
    ) -> list[RecommendationIssue]:
        if self._llm is None or not self._llm.enabled or intent is None or intent.is_empty:
            return []
        outfits: list[dict[str, Any]] = [
            {
                "index": idx,
                "items": [f"{item.color} {item.item_type}" for item in rec.items],
                "explanation": rec.overall_explanation,
            }
            for idx, rec in enumerate(recommendations)
        ]
        summary_parts = []
        if intent.occasion:
            summary_parts.append(f"occasion: {intent.occasion}")
        if intent.climate:
            summary_parts.append(f"climate: {intent.climate}")
        if intent.dress_code:
            summary_parts.append(f"dress code: {intent.dress_code}")
        try:
            return await self._llm.critique_recommendations(
                detected=base_desc,
                intent_summary="; ".join(summary_parts),
                outfits=outfits,
            )
        except LLMError as exc:
            logger.warning("verifier_llm_critique_failed", error=str(exc))
            return []

    # ── Agent entrypoint ─────────────────────────────────────────────

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        attrs = ctx.clothing_attributes
        if attrs is None or not ctx.recommendations:
            ctx.metadata["verifier_issues"] = []
            return ctx

        shopping_intent = normalize_shopping_intent(ctx.shopping_intent or ctx.gender)
        intent = intent_from_context(ctx)
        avoid_items = set(intent.avoid_items) if intent else set()
        budget = intent.budget_total_inr if intent else None

        issues: list[RecommendationIssue] = []
        for idx, rec in enumerate(ctx.recommendations):
            if not isinstance(rec, Recommendation):
                continue
            issues.extend(self._check_structure(idx, rec, attrs.clothing_type))
            issues.extend(self._check_items(idx, rec, shopping_intent, avoid_items))
            issues.extend(self._check_budget(idx, rec, budget))
            issues.extend(self._check_explanation_claims(idx, rec, attrs.clothing_type))

        issues.extend(
            await self._llm_critique(
                [r for r in ctx.recommendations if isinstance(r, Recommendation)],
                base_desc=f"{attrs.primary_color.value} {attrs.clothing_type.value}",
                intent=intent,
            )
        )

        ctx.metadata["verifier_issues"] = [issue.model_dump(mode="json") for issue in issues]

        logger.info(
            "verifier_complete",
            num_issues=len(issues),
            fixable=sum(1 for i in issues if i.fixable),
            codes=sorted({i.code for i in issues}),
        )
        return ctx
