"""Vision Agent — wraps VisionService to populate clothing attributes in context."""

from __future__ import annotations

from backend.agents.base import AgentContext, BaseAgent
from backend.core.exceptions import AgentError
from backend.services.vision import VisionService


class VisionAgent(BaseAgent):
    """Analyzes an uploaded image using CLIP + BLIP and writes
    ``ClothingAttributes`` into the shared ``AgentContext``.
    """

    name = "vision"

    def __init__(self, vision_service: VisionService) -> None:
        super().__init__()
        self._vision = vision_service

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        if ctx.image_bytes is None:
            raise AgentError("VisionAgent received no image data")

        result = await self._vision.analyze_image(ctx.image_bytes)
        ctx.clothing_attributes = result.attributes
        # Reusable by downstream stages (product reranking, wardrobe search).
        ctx.metadata["image_embedding"] = result.image_embedding
        return ctx
