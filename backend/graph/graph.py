"""LangGraph analysis pipeline — planner-routed, with a verifier retry cycle.

Graph topology::

    START → intent → vision → styling → recommendation → [wardrobe] ─┬→ [shopping] ─┐
                                              ▲                       │              ├→ verifier ─┬→ END
                                              │                       └──────────────┘            │
                                              └────────────── fixable issues, 1 retry ────────────┘

Routing is decided per request:

- wardrobe runs only for identified users (it needs a closet to search);
  failures are swallowed — it is an enhancement, not a dependency
- shopping is skipped when the client disabled products, the parsed intent
  says the user doesn't want shopping, or no product tool is configured
- the verifier can send the flow back to recommendation exactly once when it
  finds *fixable* issues (forbidden/duplicate items, unsupported claims); the
  offending item types are removed from the style matches before the rebuild

Error semantics match the pre-graph orchestrator: a vision failure is fatal
(propagates), any later agent failure ends the run with partial results, and
an intent failure is ignored entirely (intent is an enhancement, not a
dependency).
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.base import AgentContext, BaseAgent
from backend.agents.intent_agent import intent_from_context
from backend.core.logging import get_logger
from backend.schemas.intent import FIXABLE_ISSUE_CODES

logger = get_logger(__name__)

# One corrective rebuild, then ship whatever we have.
MAX_VERIFY_ATTEMPTS = 1


class PipelineState(TypedDict):
    """State flowing through the graph.

    ``ctx`` is the same mutable AgentContext the agents have always shared;
    the graph adds routing bookkeeping around it.
    """

    ctx: AgentContext
    verify_attempts: int
    pipeline_failed: bool


class AnalysisGraph:
    """Compiled LangGraph pipeline over the existing agents."""

    def __init__(
        self,
        *,
        intent_agent: BaseAgent,
        vision_agent: BaseAgent,
        styling_agent: BaseAgent,
        recommendation_agent: BaseAgent,
        wardrobe_agent: BaseAgent | None,
        shopping_agent: BaseAgent,
        verifier_agent: BaseAgent,
        has_product_tool: bool,
    ) -> None:
        self._intent = intent_agent
        self._vision = vision_agent
        self._styling = styling_agent
        self._recommendation = recommendation_agent
        self._wardrobe = wardrobe_agent
        self._shopping = shopping_agent
        self._verifier = verifier_agent
        self._has_product_tool = has_product_tool
        self.compiled = self._build()

    # ── Nodes ─────────────────────────────────────────────────────────

    async def _intent_node(self, state: PipelineState) -> dict[str, Any]:
        try:
            ctx = await self._intent.run(state["ctx"])
        except Exception as exc:  # intent is an enhancement — never fatal
            logger.warning("intent_node_failed", error=str(exc))
            return {"ctx": state["ctx"]}
        return {"ctx": ctx}

    async def _vision_node(self, state: PipelineState) -> dict[str, Any]:
        # Fatal on failure by design: no attributes, no analysis.
        ctx = await self._vision.run(state["ctx"])
        return {"ctx": ctx}

    async def _run_non_fatal(self, agent: BaseAgent, state: PipelineState) -> dict[str, Any]:
        try:
            ctx = await agent.run(state["ctx"])
        except Exception:
            # Error text already recorded in ctx.errors by BaseAgent.run().
            return {"ctx": state["ctx"], "pipeline_failed": True}
        return {"ctx": ctx}

    async def _styling_node(self, state: PipelineState) -> dict[str, Any]:
        return await self._run_non_fatal(self._styling, state)

    async def _recommendation_node(self, state: PipelineState) -> dict[str, Any]:
        ctx = state["ctx"]
        if state["verify_attempts"] > 0:
            self._apply_verifier_fixes(ctx)
        return await self._run_non_fatal(self._recommendation, state)

    async def _wardrobe_node(self, state: PipelineState) -> dict[str, Any]:
        assert self._wardrobe is not None
        try:
            ctx = await self._wardrobe.run(state["ctx"])
        except Exception as exc:  # closet unavailable — recommendations stand
            logger.warning("wardrobe_node_failed", error=str(exc))
            return {"ctx": state["ctx"]}
        return {"ctx": ctx}

    async def _shopping_node(self, state: PipelineState) -> dict[str, Any]:
        return await self._run_non_fatal(self._shopping, state)

    async def _verifier_node(self, state: PipelineState) -> dict[str, Any]:
        update = await self._run_non_fatal(self._verifier, state)
        # A verifier crash must not kill the run — recommendations stand.
        update.pop("pipeline_failed", None)
        update["verify_attempts"] = state["verify_attempts"] + 1
        return update

    @staticmethod
    def _apply_verifier_fixes(ctx: AgentContext) -> None:
        """Tighten constraints before a corrective rebuild.

        Item types the verifier flagged as forbidden/duplicate (or wrongly
        claimed in explanations) are removed from the style matches so the
        rebuilt looks cannot repeat the mistake.
        """
        issues = ctx.metadata.get("verifier_issues") or []
        flagged = {
            issue["item_type"]
            for issue in issues
            if issue.get("item_type") and issue.get("code") in FIXABLE_ISSUE_CODES
        }
        if not flagged:
            return
        before = len(ctx.style_matches)
        ctx.style_matches = [m for m in ctx.style_matches if m.item_type not in flagged]
        logger.info(
            "verifier_fixes_applied",
            removed_item_types=sorted(flagged),
            matches_before=before,
            matches_after=len(ctx.style_matches),
        )

    # ── Routing ───────────────────────────────────────────────────────

    def _after_styling(self, state: PipelineState) -> str:
        return END if state["pipeline_failed"] else "recommendation"

    def _shopping_or_verifier(self, state: PipelineState) -> str:
        ctx = state["ctx"]
        intent = intent_from_context(ctx)
        wants_shopping = intent.wants_shopping if intent else True
        if ctx.include_products and wants_shopping and self._has_product_tool:
            return "shopping"
        return "verifier"

    def _after_recommendation(self, state: PipelineState) -> str:
        if state["pipeline_failed"]:
            return END
        if self._wardrobe is not None and state["ctx"].user_id:
            return "wardrobe"
        return self._shopping_or_verifier(state)

    def _after_wardrobe(self, state: PipelineState) -> str:
        return self._shopping_or_verifier(state)

    def _after_shopping(self, state: PipelineState) -> str:
        return END if state["pipeline_failed"] else "verifier"

    def _after_verifier(self, state: PipelineState) -> str:
        issues = state["ctx"].metadata.get("verifier_issues") or []
        has_fixable = any(issue.get("item_type") and issue.get("code") in FIXABLE_ISSUE_CODES for issue in issues)
        if has_fixable and state["verify_attempts"] <= MAX_VERIFY_ATTEMPTS:
            logger.info("verifier_retry", attempt=state["verify_attempts"])
            return "recommendation"
        return END

    # ── Build ─────────────────────────────────────────────────────────

    def _build(self) -> Any:
        graph: StateGraph[PipelineState] = StateGraph(PipelineState)
        graph.add_node("intent", self._intent_node)
        graph.add_node("vision", self._vision_node)
        graph.add_node("styling", self._styling_node)
        graph.add_node("recommendation", self._recommendation_node)
        if self._wardrobe is not None:
            graph.add_node("wardrobe", self._wardrobe_node)
        graph.add_node("shopping", self._shopping_node)
        graph.add_node("verifier", self._verifier_node)

        graph.add_edge(START, "intent")
        graph.add_edge("intent", "vision")
        graph.add_edge("vision", "styling")
        graph.add_conditional_edges("styling", self._after_styling, {"recommendation": "recommendation", END: END})
        recommendation_targets: dict[Hashable, str] = {"shopping": "shopping", "verifier": "verifier", END: END}
        if self._wardrobe is not None:
            recommendation_targets["wardrobe"] = "wardrobe"
            graph.add_conditional_edges(
                "wardrobe", self._after_wardrobe, {"shopping": "shopping", "verifier": "verifier"}
            )
        graph.add_conditional_edges("recommendation", self._after_recommendation, recommendation_targets)
        graph.add_conditional_edges("shopping", self._after_shopping, {"verifier": "verifier", END: END})
        graph.add_conditional_edges("verifier", self._after_verifier, {"recommendation": "recommendation", END: END})
        return graph.compile()

    # ── Public API ────────────────────────────────────────────────────

    @staticmethod
    def initial_state(ctx: AgentContext) -> PipelineState:
        return PipelineState(ctx=ctx, verify_attempts=0, pipeline_failed=False)

    async def run(self, ctx: AgentContext) -> AgentContext:
        final = await self.compiled.ainvoke(self.initial_state(ctx))
        result_ctx: AgentContext = final["ctx"]
        return result_ctx
