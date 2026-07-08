"""Base agent protocol and shared context for the multi-agent pipeline."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from backend.core.logging import get_logger
from backend.core.tracing import get_tracer
from backend.schemas.clothing import ClothingAttributes

logger = get_logger(__name__)


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class StyleMatch:
    """A single styling suggestion produced by the Styling Agent."""

    item_type: str
    recommended_colors: list[str]
    recommended_styles: list[str]
    match_score: float
    rule_source: str


@dataclass
class AgentContext:
    """Mutable context that flows through the agent pipeline.

    Each agent reads from and writes to this context so downstream
    agents can consume the results of upstream agents.
    """

    request_id: UUID = field(default_factory=uuid4)

    # Input
    image_bytes: bytes | None = None
    user_id: str | None = None
    gender: str = "unisex"
    shopping_intent: str | None = None
    include_products: bool = True

    # Vision Agent output
    clothing_attributes: ClothingAttributes | None = None

    # Styling Agent output
    style_matches: list[StyleMatch] = field(default_factory=list)

    # Recommendation Agent output — populated as list[Recommendation] (api schema)
    recommendations: list[Any] = field(default_factory=list)

    # Telemetry / debugging
    errors: list[str] = field(default_factory=list)
    agent_timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base for every agent in the pipeline."""

    name: str = "base"

    def __init__(self) -> None:
        self.state = AgentState.IDLE

    @abstractmethod
    async def _execute(self, ctx: AgentContext) -> AgentContext:
        """Subclass-specific logic.  Must return the (possibly mutated) context."""
        ...

    async def run(self, ctx: AgentContext) -> AgentContext:
        """Run the agent with state tracking, timing, tracing, and error handling."""
        self.state = AgentState.RUNNING
        logger.info("agent_start", agent=self.name, request_id=str(ctx.request_id))
        t0 = time.perf_counter()

        with get_tracer().span(
            f"agent.{self.name}",
            as_type="agent",
            metadata={"request_id": str(ctx.request_id)},
        ) as span:
            try:
                ctx = await self._execute(ctx)
                self.state = AgentState.DONE
            except Exception as exc:
                self.state = AgentState.ERROR
                ctx.errors.append(f"{self.name}: {exc}")
                logger.error("agent_error", agent=self.name, error=str(exc))
                raise
            finally:
                elapsed = round(time.perf_counter() - t0, 3)
                ctx.agent_timings[self.name] = elapsed
                if span is not None:
                    span.update(output={"state": self.state.value, "elapsed_s": elapsed})
                logger.info(
                    "agent_finish",
                    agent=self.name,
                    state=self.state.value,
                    elapsed_s=elapsed,
                )

        return ctx
