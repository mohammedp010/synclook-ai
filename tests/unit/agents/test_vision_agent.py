"""Unit tests for VisionAgent."""

import pytest
from unittest.mock import AsyncMock

from backend.agents.base import AgentContext, AgentState
from backend.agents.vision_agent import VisionAgent
from backend.core.exceptions import AgentError
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


class TestVisionAgent:
    """Tests for VisionAgent with mocked VisionService."""

    @pytest.fixture
    def vision_service(self) -> AsyncMock:
        svc = AsyncMock()
        svc.analyze_image = AsyncMock(
            return_value=ClothingAttributes(
                clothing_type=ClothingType.JEANS,
                primary_color=Color.BLUE,
                pattern=Pattern.SOLID,
                style=Style.CASUAL,
                confidence=0.9,
                description="blue denim jeans",
            )
        )
        return svc

    @pytest.fixture
    def agent(self, vision_service: AsyncMock) -> VisionAgent:
        return VisionAgent(vision_service)

    async def test_run_populates_attributes(self, agent: VisionAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake-image")
        result = await agent.run(ctx)
        assert result.clothing_attributes is not None
        assert result.clothing_attributes.clothing_type == ClothingType.JEANS
        assert result.clothing_attributes.primary_color == Color.BLUE

    async def test_run_calls_vision_service(self, agent: VisionAgent, vision_service: AsyncMock) -> None:
        ctx = AgentContext(image_bytes=b"test-bytes")
        await agent.run(ctx)
        vision_service.analyze_image.assert_called_once_with(b"test-bytes")

    async def test_run_with_no_image_raises(self, agent: VisionAgent) -> None:
        ctx = AgentContext(image_bytes=None)
        with pytest.raises(AgentError, match="no image data"):
            await agent.run(ctx)

    async def test_agent_state_transitions(self, agent: VisionAgent) -> None:
        assert agent.state == AgentState.IDLE
        ctx = AgentContext(image_bytes=b"fake")
        await agent.run(ctx)
        assert agent.state == AgentState.DONE

    async def test_agent_state_error_on_failure(self, vision_service: AsyncMock) -> None:
        vision_service.analyze_image.side_effect = Exception("model crash")
        agent = VisionAgent(vision_service)
        ctx = AgentContext(image_bytes=b"fake")
        with pytest.raises(Exception, match="model crash"):
            await agent.run(ctx)
        assert agent.state == AgentState.ERROR

    async def test_timing_recorded(self, agent: VisionAgent) -> None:
        ctx = AgentContext(image_bytes=b"fake")
        result = await agent.run(ctx)
        assert "vision" in result.agent_timings
        assert result.agent_timings["vision"] >= 0

    async def test_name_attribute(self, agent: VisionAgent) -> None:
        assert agent.name == "vision"
