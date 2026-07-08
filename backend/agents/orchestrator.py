"""Orchestrator — chains agents and manages the analysis pipeline.

Runs VisionAgent → StylingAgent → RecommendationAgent in sequence,
passing a shared AgentContext through each stage.  Provides error
recovery so that partial results are returned if a downstream agent fails.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator

from backend.agents.base import AgentContext, BaseAgent
from backend.agents.recommendation_agent import RecommendationAgent
from backend.agents.shopping_agent import ShoppingAgent
from backend.agents.styling_agent import StylingAgent
from backend.agents.vision_agent import VisionAgent
from backend.core.logging import get_logger
from backend.core.tracing import get_tracer
from backend.services.fashion_knowledge import FashionKnowledgeService
from backend.services.llm import LLMService
from backend.services.memory import MemoryService
from backend.services.vision import VisionService
from backend.tools.product_search import ProductSearchTool

logger = get_logger(__name__)


class Orchestrator:
    """Chains the multi-agent pipeline and manages context lifecycle.

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
        self._pipeline: list[BaseAgent] = [
            VisionAgent(vision_service),
            StylingAgent(fashion_knowledge=knowledge),
            RecommendationAgent(llm_service=llm_service, fashion_knowledge=knowledge),
            ShoppingAgent(product_tool=product_tool),
        ]
        self._memory = memory_service

    async def run(
        self,
        image_bytes: bytes,
        *,
        user_id: str | None = None,
        gender: str = "unisex",
        shopping_intent: str | None = None,
        include_products: bool = True,
    ) -> AgentContext:
        """Execute the full agent pipeline and return the final context.

        If VisionAgent fails the error is re-raised (no image = no analysis).
        If a downstream agent (Styling / Recommendation / Shopping) fails, partial
        results collected so far are returned and the error is recorded
        in ``ctx.errors``.
        """
        ctx = AgentContext(
            image_bytes=image_bytes,
            user_id=user_id,
            gender=gender,
            shopping_intent=shopping_intent,
            include_products=include_products,
        )
        t0 = time.perf_counter()

        logger.info(
            "orchestrator_start",
            request_id=str(ctx.request_id),
            user_id=user_id,
            num_agents=len(self._pipeline),
        )

        # Load user preferences from memory (if available)
        if self._memory and user_id:
            try:
                prefs = await self._memory.get_preferences(user_id)
                ctx.metadata["user_preferences"] = prefs.to_dict()
                logger.info("memory_loaded", user_id=user_id, prefs=prefs.to_dict())
            except Exception as exc:
                logger.warning("memory_load_failed", error=str(exc))

        with get_tracer().span(
            "analysis.pipeline",
            metadata={"request_id": str(ctx.request_id), "user_id": user_id},
        ) as root_span:
            for agent in self._pipeline:
                try:
                    ctx = await agent.run(ctx)
                except Exception as exc:
                    # Vision failure is fatal — can't proceed without attributes
                    if agent.name == "vision":
                        logger.error(
                            "orchestrator_fatal",
                            agent=agent.name,
                            error=str(exc),
                            request_id=str(ctx.request_id),
                        )
                        raise

                    # Downstream failures are non-fatal — return partial results
                    logger.warning(
                        "orchestrator_partial",
                        agent=agent.name,
                        error=str(exc),
                        request_id=str(ctx.request_id),
                    )
                    # Error already recorded in ctx.errors by BaseAgent.run()
                    break

            if root_span is not None:
                root_span.update(
                    output={
                        "num_recommendations": len(ctx.recommendations),
                        "errors": ctx.errors or None,
                    }
                )

        elapsed = round(time.perf_counter() - t0, 3)
        ctx.metadata["total_elapsed_s"] = elapsed

        # Save analysis to user history (if available)
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
    ) -> AsyncGenerator[dict[str, str], None]:
        """Execute the pipeline while yielding SSE-friendly progress events.

        Each yielded dict has ``event`` and ``data`` keys suitable for
        ``sse_starlette.EventSourceResponse``.
        """
        ctx = AgentContext(
            image_bytes=image_bytes,
            user_id=user_id,
            gender=gender,
            shopping_intent=shopping_intent,
            include_products=include_products,
        )
        t0 = time.perf_counter()
        request_id = str(ctx.request_id)

        yield {
            "event": "status",
            "data": json.dumps({"stage": "start", "message": "Analysis started", "request_id": request_id}),
        }

        # Load user preferences
        if self._memory and user_id:
            try:
                prefs = await self._memory.get_preferences(user_id)
                ctx.metadata["user_preferences"] = prefs.to_dict()
            except Exception:
                pass

        agent_labels = {
            "vision": "Analyzing image...",
            "styling": "Generating style matches...",
            "recommendation": "Building recommendations...",
            "shopping": "Finding products online...",
        }

        for agent in self._pipeline:
            label = agent_labels.get(agent.name, agent.name)
            yield {"event": "status", "data": json.dumps({"stage": agent.name, "message": label})}

            try:
                ctx = await agent.run(ctx)
            except Exception as exc:
                if agent.name == "vision":
                    yield {"event": "error", "data": json.dumps({"stage": agent.name, "error": str(exc)})}
                    return
                yield {"event": "warning", "data": json.dumps({"stage": agent.name, "error": str(exc)})}
                break

            yield {
                "event": "agent_done",
                "data": json.dumps({"stage": agent.name, "message": f"{agent.name} complete"}),
            }

        # Save to memory
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
            except Exception:
                pass

        elapsed = round(time.perf_counter() - t0, 3)
        ctx.metadata["total_elapsed_s"] = elapsed

        # Build final result payload
        result = {
            "request_id": request_id,
            "detected_attributes": ctx.clothing_attributes.model_dump(mode="json") if ctx.clothing_attributes else None,
            "recommendations": [
                rec.model_dump(mode="json") if hasattr(rec, "model_dump") else rec for rec in ctx.recommendations
            ],
            "errors": ctx.errors or None,
        }

        yield {"event": "result", "data": json.dumps(result, default=str)}
        yield {"event": "done", "data": json.dumps({"elapsed_s": elapsed})}
