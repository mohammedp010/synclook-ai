"""Integration tests for the LangGraph pipeline: routing, retry, and intent effects."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from backend.agents import Orchestrator
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)
from backend.services.vision import VisionResult


def _vision_svc(clothing_type: ClothingType = ClothingType.TROUSERS, style: Style = Style.CASUAL) -> AsyncMock:
    svc = AsyncMock()
    svc.analyze_image = AsyncMock(
        return_value=VisionResult(
            attributes=ClothingAttributes(
                clothing_type=clothing_type,
                primary_color=Color.BLACK,
                pattern=Pattern.SOLID,
                style=style,
                confidence=0.9,
            ),
            image_embedding=[0.1] * 8,
        )
    )
    return svc


class TestPlannerRouting:
    async def test_shopping_skipped_without_product_tool(self) -> None:
        orch = Orchestrator(vision_service=_vision_svc())
        ctx = await orch.run(b"img")
        assert "shopping" not in ctx.agent_timings
        assert "verifier" in ctx.agent_timings

    async def test_shopping_skipped_when_intent_declines(self) -> None:
        """'no shopping' in the request routes past the shopping node."""
        tool = AsyncMock()
        orch = Orchestrator(vision_service=_vision_svc(), product_tool=tool)
        ctx = await orch.run(b"img", user_intent="casual look, no shopping links")
        assert "shopping" not in ctx.agent_timings
        tool.find_products.assert_not_called()

    async def test_shopping_runs_with_tool_and_default_intent(self) -> None:
        tool = AsyncMock()
        tool.find_products = AsyncMock(return_value=[])
        orch = Orchestrator(vision_service=_vision_svc(), product_tool=tool)
        ctx = await orch.run(b"img")
        assert "shopping" in ctx.agent_timings


class TestIntentChangesOutfits:
    """Same image, different stated intent ⇒ meaningfully different outfits."""

    async def test_office_vs_gym_produce_different_items(self) -> None:
        orch = Orchestrator(vision_service=_vision_svc(ClothingType.TROUSERS, Style.CASUAL))

        office_ctx = await orch.run(b"img", user_intent="style this for the office")
        gym_ctx = await orch.run(b"img", user_intent="style this for the gym")

        office_items = {i.item_type for r in office_ctx.recommendations for i in r.items}
        gym_items = {i.item_type for r in gym_ctx.recommendations for i in r.items}

        assert office_ctx.metadata["effective_style"] == "smart_casual"
        assert gym_ctx.metadata["effective_style"] == "sporty"
        assert office_items != gym_items

    async def test_avoid_list_is_respected(self) -> None:
        orch = Orchestrator(vision_service=_vision_svc(ClothingType.TROUSERS, Style.SMART_CASUAL))
        # Heuristic parsing has no avoid-list extraction, so seed via metadata
        # the way the LLM extraction path would.
        ctx = await orch.run(b"img")
        baseline_items = {i.item_type for r in ctx.recommendations for i in r.items}
        assert "shirt" in baseline_items

        orch2 = Orchestrator(vision_service=_vision_svc(ClothingType.TROUSERS, Style.SMART_CASUAL))
        llm = AsyncMock()
        llm.enabled = True
        from backend.schemas.intent import StyleIntent

        llm.extract_intent = AsyncMock(return_value=StyleIntent(avoid_items=["shirt"]))
        orch2._graph._intent._llm = llm  # inject the mocked extractor
        ctx2 = await orch2.run(b"img", user_intent="anything but shirts")
        items2 = {i.item_type for r in ctx2.recommendations for i in r.items}
        assert "shirt" not in items2


class TestVerifierRetryCycle:
    async def test_forbidden_item_triggers_one_rebuild(self) -> None:
        """Seed a policy violation and confirm the graph loops back once."""
        orch = Orchestrator(vision_service=_vision_svc(ClothingType.TROUSERS, Style.CASUAL))

        recommendation_agent = orch._graph._recommendation
        original_execute = recommendation_agent._execute
        call_count = 0

        async def sabotage_then_behave(ctx):
            nonlocal call_count
            call_count += 1
            ctx = await original_execute(ctx)
            if call_count == 1 and ctx.recommendations:
                # Inject a menswear-forbidden item into the first look.
                from backend.schemas.api import RecommendationItem

                ctx.recommendations[0].items.append(
                    RecommendationItem(item_type="blouse", color="white", style="casual", reason="seeded")
                )
            return ctx

        recommendation_agent._execute = sabotage_then_behave

        ctx = await orch.run(b"img", gender="menswear", shopping_intent="menswear")

        assert call_count == 2, "verifier should have sent the flow back exactly once"
        final_items = {i.item_type for r in ctx.recommendations for i in r.items}
        assert "blouse" not in final_items

    async def test_stream_includes_intent_and_verifier_stages(self) -> None:
        orch = Orchestrator(vision_service=_vision_svc())
        events = []
        async for event in orch.run_stream(b"img", user_intent="casual weekend look"):
            events.append(event)
        stages = [json.loads(e["data"])["stage"] for e in events if e["event"] == "agent_done"]
        assert stages[0] == "intent"
        assert stages[-1] == "verifier"
        assert [e["event"] for e in events][-1] == "done"


@pytest.mark.asyncio
async def test_graph_survives_verifier_crash() -> None:
    """A verifier failure must never take down the run."""
    orch = Orchestrator(vision_service=_vision_svc())

    async def boom(ctx):
        raise RuntimeError("verifier exploded")

    orch._graph._verifier._execute = boom
    ctx = await orch.run(b"img")
    assert ctx.recommendations, "recommendations should survive a verifier crash"
