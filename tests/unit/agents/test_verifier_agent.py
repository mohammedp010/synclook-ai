"""Tests for the VerifierAgent's deterministic quality checks."""

from __future__ import annotations

from uuid import uuid4

from backend.agents.base import AgentContext
from backend.agents.verifier_agent import VerifierAgent, _parse_price
from backend.schemas.api import ProductLink, Recommendation, RecommendationItem
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


def _ctx(base_type: ClothingType = ClothingType.TROUSERS, intent: dict | None = None) -> AgentContext:
    ctx = AgentContext(image_bytes=b"x", gender="menswear", shopping_intent="menswear")
    ctx.clothing_attributes = ClothingAttributes(
        clothing_type=base_type,
        primary_color=Color.BLACK,
        pattern=Pattern.SOLID,
        style=Style.SMART_CASUAL,
        confidence=0.9,
    )
    if intent is not None:
        ctx.metadata["intent"] = intent
    return ctx


def _item(item_type: str, **kwargs) -> RecommendationItem:
    defaults = {"color": "white", "style": "smart_casual", "reason": "r"}
    defaults.update(kwargs)
    return RecommendationItem(item_type=item_type, **defaults)


def _rec(items: list[RecommendationItem], explanation: str = "A clean look.") -> Recommendation:
    return Recommendation(id=uuid4(), items=items, overall_explanation=explanation)


class TestPriceParsing:
    def test_rupee_format(self) -> None:
        assert _parse_price("₹1,299") == 1299.0

    def test_plain_and_missing(self) -> None:
        assert _parse_price("2499.50") == 2499.5
        assert _parse_price("N/A") is None
        assert _parse_price("") is None


class TestVerifierChecks:
    async def test_clean_recommendation_passes(self) -> None:
        ctx = _ctx()
        ctx.recommendations = [_rec([_item("shirt"), _item("shoes")])]
        ctx = await VerifierAgent().run(ctx)
        assert ctx.metadata["verifier_issues"] == []

    async def test_incomplete_outfit_flagged(self) -> None:
        ctx = _ctx()  # trousers base requires topwear
        ctx.recommendations = [_rec([_item("shoes")])]
        ctx = await VerifierAgent().run(ctx)
        codes = {i["code"] for i in ctx.metadata["verifier_issues"]}
        assert "incomplete_outfit" in codes

    async def test_forbidden_item_flagged_for_intent_policy(self) -> None:
        ctx = _ctx()  # menswear
        ctx.recommendations = [_rec([_item("blouse"), _item("shirt")])]
        ctx = await VerifierAgent().run(ctx)
        issues = ctx.metadata["verifier_issues"]
        assert any(i["code"] == "forbidden_item" and i["item_type"] == "blouse" for i in issues)

    async def test_avoid_list_item_flagged(self) -> None:
        ctx = _ctx(intent={"avoid_items": ["shirt"]})
        ctx.recommendations = [_rec([_item("shirt"), _item("shoes")])]
        ctx = await VerifierAgent().run(ctx)
        issues = ctx.metadata["verifier_issues"]
        assert any(i["code"] == "forbidden_item" and i["item_type"] == "shirt" for i in issues)

    async def test_duplicate_item_flagged(self) -> None:
        ctx = _ctx()
        ctx.recommendations = [_rec([_item("shirt"), _item("shirt")])]
        ctx = await VerifierAgent().run(ctx)
        codes = {i["code"] for i in ctx.metadata["verifier_issues"]}
        assert "duplicate_item" in codes

    async def test_budget_exceeded_flagged(self) -> None:
        product = ProductLink(title="Shirt", price="₹4,000", link="l", thumbnail="t", source="s")
        item = _item("shirt", products=[product])
        ctx = _ctx(intent={"budget_total_inr": 1000})
        ctx.recommendations = [_rec([item])]
        ctx = await VerifierAgent().run(ctx)
        codes = {i["code"] for i in ctx.metadata["verifier_issues"]}
        assert "budget_exceeded" in codes

    async def test_owned_items_excluded_from_budget(self) -> None:
        product = ProductLink(title="Shirt", price="₹4,000", link="l", thumbnail="t", source="s")
        item = _item("shirt", products=[product], owned=True)
        ctx = _ctx(intent={"budget_total_inr": 1000})
        ctx.recommendations = [_rec([item])]
        ctx = await VerifierAgent().run(ctx)
        codes = {i["code"] for i in ctx.metadata["verifier_issues"]}
        assert "budget_exceeded" not in codes

    async def test_unsupported_claim_flagged(self) -> None:
        ctx = _ctx()
        ctx.recommendations = [_rec([_item("shirt")], explanation="Pair it with a lovely blazer and shirt.")]
        ctx = await VerifierAgent().run(ctx)
        issues = ctx.metadata["verifier_issues"]
        assert any(i["code"] == "unsupported_claim" and i["item_type"] == "blazer" for i in issues)

    async def test_tshirt_does_not_trigger_shirt_claim(self) -> None:
        """'t-shirt' in the explanation must not read as an unsupported 'shirt'."""
        ctx = _ctx()
        ctx.recommendations = [_rec([_item("t-shirt")], explanation="A crisp t-shirt anchors the look.")]
        ctx = await VerifierAgent().run(ctx)
        codes = {i["code"] for i in ctx.metadata["verifier_issues"]}
        assert "unsupported_claim" not in codes

    async def test_no_recommendations_is_clean(self) -> None:
        ctx = _ctx()
        ctx.recommendations = []
        ctx = await VerifierAgent().run(ctx)
        assert ctx.metadata["verifier_issues"] == []
