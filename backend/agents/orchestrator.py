"""Orchestrator — façade over the LangGraph analysis pipeline.

Builds the compiled graph (intent → vision → styling → recommendation →
shopping → verifier, with planner routing and a verifier retry cycle) and
exposes the same ``run()`` / ``run_stream()`` surface the API routes have
always used. Memory (user preferences / history) is handled here, around the
graph invocation.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator

from backend.agents.base import AgentContext
from backend.agents.intent_agent import IntentAgent
from backend.agents.recommendation_agent import RecommendationAgent
from backend.agents.shopping_agent import ShoppingAgent
from backend.agents.styling_agent import StylingAgent
from backend.agents.verifier_agent import VerifierAgent
from backend.agents.vision_agent import VisionAgent
from backend.core.logging import get_logger
from backend.core.tracing import get_tracer
from backend.graph import AnalysisGraph
from backend.services.fashion_knowledge import FashionKnowledgeService
from backend.services.llm import LLMService
from backend.services.memory import MemoryService
from backend.services.vision import VisionService
from backend.tools.product_search import ProductSearchTool

logger = get_logger(__name__)

_AGENT_LABELS = {
    "intent": "Understanding your request...",
    "vision": "Analyzing image...",
    "styling": "Generating style matches...",
    "recommendation": "Building recommendations...",
    "shopping": "Finding products online...",
    "verifier": "Quality-checking recommendations...",
}


class Orchestrator:
    """Runs the agentic analysis graph and manages context lifecycle.

    Usage::

        orch = Orchestrator(vision_service, llm_service, memory_service)
        ctx = await orch.run(image_bytes, user_id="u123")
    """

    def __init__(
        self,
        vision_service: VisionService,
        llm_service: LLMService | None = None,
        memory_service: MemoryService | None = None,
        product_tool: ProductSearchTool | None = None,
        fashion_knowledge: FashionKnowledgeService | None = None,
    ) -> None:
        knowledge = fashion_knowledge or FashionKnowledgeService()
        self._memory = memory_service
        self._graph = AnalysisGraph(
            intent_agent=IntentAgent(llm_service=llm_service),
            vision_agent=VisionAgent(vision_service),
            styling_agent=StylingAgent(fashion_knowledge=knowledge),
            recommendation_agent=RecommendationAgent(llm_service=llm_service, fashion_knowledge=knowledge),
            shopping_agent=ShoppingAgent(product_tool=product_tool),
            verifier_agent=VerifierAgent(llm_service=llm_service),
            has_product_tool=product_tool is not None,
        )

    def _make_context(
        self,
        image_bytes: bytes,
        *,
        user_id: str | None,
        gender: str,
        shopping_intent: str | None,
        include_products: bool,
        user_intent: str | None,
    ) -> AgentContext:
        ctx = AgentContext(
            image_bytes=image_bytes,
            user_id=user_id,
            gender=gender,
            shopping_intent=shopping_intent,
            include_products=include_products,
        )
        if user_intent:
            ctx.metadata["user_intent_text"] = user_intent
        return ctx

    async def _load_preferences(self, ctx: AgentContext, user_id: str | None) -> None:
        if self._memory and user_id:
            try:
                prefs = await self._memory.get_preferences(user_id)
                ctx.metadata["user_preferences"] = prefs.to_dict()
                logger.info("memory_loaded", user_id=user_id)
            except Exception as exc:
                logger.warning("memory_load_failed", error=str(exc))

    async def _save_history(self, ctx: AgentContext, user_id: str | None) -> None:
        if self._memory and user_id and ctx.clothing_attributes:
            try:
                attrs = ctx.clothing_attributes
                await self._memory.save_analysis(
                    user_id,
                    clothing_type=attrs.clothing_type.value,
                    color=attrs.primary_color.value,
                    style=attrs.style.value,
                    pattern=attrs.pattern.value,
                )
                logger.info("memory_analysis_saved", user_id=user_id)
            except Exception as exc:
                logger.warning("memory_save_failed", error=str(exc))

    async def run(
        self,
        image_bytes: bytes,
        *,
        user_id: str | None = None,
        gender: str = "unisex",
        shopping_intent: str | None = None,
        include_products: bool = True,
        user_intent: str | None = None,
    ) -> AgentContext:
        """Execute the analysis graph and return the final context.

        If the vision stage fails the error is re-raised (no image = no
        analysis). Any later stage failure ends the run with partial results
        and the error recorded in ``ctx.errors``.
        """
        ctx = self._make_context(
            image_bytes,
            user_id=user_id,
            gender=gender,
            shopping_intent=shopping_intent,
            include_products=include_products,
            user_intent=user_intent,
        )
        t0 = time.perf_counter()
        logger.info("orchestrator_start", request_id=str(ctx.request_id), user_id=user_id)

        await self._load_preferences(ctx, user_id)

        with get_tracer().span(
            "analysis.pipeline",
            metadata={"request_id": str(ctx.request_id), "user_id": user_id},
        ) as root_span:
            ctx = await self._graph.run(ctx)
            if root_span is not None:
                root_span.update(
                    output={
                        "num_recommendations": len(ctx.recommendations),
                        "errors": ctx.errors or None,
                    }
                )

        elapsed = round(time.perf_counter() - t0, 3)
        ctx.metadata["total_elapsed_s"] = elapsed

        await self._save_history(ctx, user_id)

        logger.info(
            "orchestrator_complete",
            request_id=str(ctx.request_id),
            total_elapsed_s=elapsed,
            num_recommendations=len(ctx.recommendations),
            errors=ctx.errors or None,
        )
        return ctx

    async def run_stream(
        self,
        image_bytes: bytes,
        *,
        user_id: str | None = None,
        gender: str = "unisex",
        shopping_intent: str | None = None,
        include_products: bool = True,
        user_intent: str | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Execute the graph while yielding SSE-friendly progress events.

        Each yielded dict has ``event`` and ``data`` keys suitable for
        ``sse_starlette.EventSourceResponse``.
        """
        ctx = self._make_context(
            image_bytes,
            user_id=user_id,
            gender=gender,
            shopping_intent=shopping_intent,
            include_products=include_products,
            user_intent=user_intent,
        )
        t0 = time.perf_counter()
        request_id = str(ctx.request_id)

        yield {
            "event": "status",
            "data": json.dumps({"stage": "start", "message": "Analysis started", "request_id": request_id}),
        }

        await self._load_preferences(ctx, user_id)

        try:
            async for chunk in self._graph.compiled.astream(self._graph.initial_state(ctx), stream_mode="updates"):
                for node_name, update in chunk.items():
                    if update and update.get("ctx") is not None:
                        ctx = update["ctx"]
                    label = _AGENT_LABELS.get(node_name, node_name)
                    yield {"event": "status", "data": json.dumps({"stage": node_name, "message": label})}
                    if update and update.get("pipeline_failed"):
                        error_text = ctx.errors[-1] if ctx.errors else f"{node_name} failed"
                        yield {"event": "warning", "data": json.dumps({"stage": node_name, "error": error_text})}
                    else:
                        yield {
                            "event": "agent_done",
                            "data": json.dumps({"stage": node_name, "message": f"{node_name} complete"}),
                        }
        except Exception as exc:
            # Vision failures are fatal by design and end the stream.
            yield {"event": "error", "data": json.dumps({"stage": "vision", "error": str(exc)})}
            return

        await self._save_history(ctx, user_id)

        elapsed = round(time.perf_counter() - t0, 3)
        ctx.metadata["total_elapsed_s"] = elapsed

        result = {
            "request_id": request_id,
            "detected_attributes": (
                ctx.clothing_attributes.model_dump(mode="json") if ctx.clothing_attributes else None
            ),
            "recommendations": [
                rec.model_dump(mode="json") if hasattr(rec, "model_dump") else rec for rec in ctx.recommendations
            ],
            "errors": ctx.errors or None,
        }

        yield {"event": "result", "data": json.dumps(result, default=str)}
        yield {"event": "done", "data": json.dumps({"elapsed_s": elapsed})}
