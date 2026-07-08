"""Integration tests for Orchestrator — full pipeline with mocked VisionService."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.base import AgentContext
from backend.agents.orchestrator import Orchestrator
from backend.core.exceptions import ImageProcessingError
from backend.schemas.api import Recommendation
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


@pytest.fixture
def mock_vision_svc() -> AsyncMock:
    svc = AsyncMock()
    svc.analyze_image = AsyncMock(
        return_value=ClothingAttributes(
            clothing_type=ClothingType.SHIRT,
            primary_color=Color.NAVY,
            pattern=Pattern.SOLID,
            style=Style.SMART_CASUAL,
            confidence=0.85,
            description="a navy dress shirt",
        )
    )
    return svc


@pytest.fixture
def orchestrator(mock_vision_svc: AsyncMock) -> Orchestrator:
    return Orchestrator(vision_service=mock_vision_svc, llm_service=None, memory_service=None)


class TestOrchestratorRun:
    """Integration tests for the synchronous pipeline."""

    async def test_full_pipeline_produces_recommendations(self, orchestrator: Orchestrator) -> None:
        ctx = await orchestrator.run(b"fake-image", user_id="test-user")
        assert ctx.clothing_attributes is not None
        assert len(ctx.style_matches) > 0
        assert len(ctx.recommendations) > 0

    async def test_recommendations_are_pydantic_models(self, orchestrator: Orchestrator) -> None:
        ctx = await orchestrator.run(b"fake-image")
        for rec in ctx.recommendations:
            assert isinstance(rec, Recommendation)

    async def test_timing_metadata(self, orchestrator: Orchestrator) -> None:
        ctx = await orchestrator.run(b"fake-image")
        assert "total_elapsed_s" in ctx.metadata
        assert "vision" in ctx.agent_timings
        assert "styling" in ctx.agent_timings
        assert "recommendation" in ctx.agent_timings

    async def test_vision_failure_is_fatal(self, mock_vision_svc: AsyncMock) -> None:
        mock_vision_svc.analyze_image.side_effect = ImageProcessingError("bad image")
        orch = Orchestrator(vision_service=mock_vision_svc)
        with pytest.raises(ImageProcessingError):
            await orch.run(b"bad-bytes")

    async def test_partial_results_on_downstream_failure(self, mock_vision_svc: AsyncMock) -> None:
        """If StylingAgent raises, vision results should still be present."""
        orch = Orchestrator(vision_service=mock_vision_svc)

        # Monkey-patch the styling agent's _execute to raise
        original_execute = orch._pipeline[1]._execute

        async def bad_execute(ctx):
            raise RuntimeError("styling crashed")

        orch._pipeline[1]._execute = bad_execute
        ctx = await orch.run(b"fake-image")

        assert ctx.clothing_attributes is not None
        # BaseAgent.run() records errors as "{name}: {exc}"
        assert any("styling" in e for e in ctx.errors)

    async def test_user_id_passed_to_context(self, orchestrator: Orchestrator) -> None:
        ctx = await orchestrator.run(b"fake", user_id="u123")
        assert ctx.user_id == "u123"

    async def test_memory_integration(self, mock_vision_svc: AsyncMock) -> None:
        """MemoryService should be called to load/save preferences."""
        from backend.services.memory import UserPreferences

        mock_memory = AsyncMock()
        mock_memory.get_preferences = AsyncMock(return_value=UserPreferences())
        mock_memory.save_analysis = AsyncMock()

        orch = Orchestrator(
            vision_service=mock_vision_svc,
            memory_service=mock_memory,
        )
        ctx = await orch.run(b"fake", user_id="mem-user")

        mock_memory.get_preferences.assert_called_once_with("mem-user")
        mock_memory.save_analysis.assert_called_once()

    async def test_memory_not_called_without_user_id(self, mock_vision_svc: AsyncMock) -> None:
        mock_memory = AsyncMock()
        orch = Orchestrator(vision_service=mock_vision_svc, memory_service=mock_memory)
        await orch.run(b"fake")
        mock_memory.get_preferences.assert_not_called()


class TestOrchestratorRunStream:
    """Integration tests for the SSE streaming pipeline."""

    async def test_stream_yields_events(self, orchestrator: Orchestrator) -> None:
        events = []
        async for event in orchestrator.run_stream(b"fake-image", user_id="stream-user"):
            events.append(event)

        event_types = [e["event"] for e in events]
        assert "status" in event_types
        assert "agent_done" in event_types
        assert "result" in event_types
        assert "done" in event_types

    async def test_stream_starts_with_start_status(self, orchestrator: Orchestrator) -> None:
        events = []
        async for event in orchestrator.run_stream(b"fake-image"):
            events.append(event)

        first = events[0]
        assert first["event"] == "status"
        data = json.loads(first["data"])
        assert data["stage"] == "start"

    async def test_stream_ends_with_done(self, orchestrator: Orchestrator) -> None:
        events = []
        async for event in orchestrator.run_stream(b"fake-image"):
            events.append(event)

        last = events[-1]
        assert last["event"] == "done"
        data = json.loads(last["data"])
        assert "elapsed_s" in data

    async def test_stream_result_contains_attributes(self, orchestrator: Orchestrator) -> None:
        events = []
        async for event in orchestrator.run_stream(b"fake-image"):
            events.append(event)

        result_events = [e for e in events if e["event"] == "result"]
        assert len(result_events) == 1
        result = json.loads(result_events[0]["data"])
        assert result["detected_attributes"] is not None
        assert result["detected_attributes"]["clothing_type"] == "shirt"

    async def test_stream_result_contains_recommendations(self, orchestrator: Orchestrator) -> None:
        events = []
        async for event in orchestrator.run_stream(b"fake-image"):
            events.append(event)

        result = json.loads([e for e in events if e["event"] == "result"][0]["data"])
        assert len(result["recommendations"]) > 0

    async def test_stream_vision_failure_emits_error(self, mock_vision_svc: AsyncMock) -> None:
        mock_vision_svc.analyze_image.side_effect = ImageProcessingError("bad image")
        orch = Orchestrator(vision_service=mock_vision_svc)

        events = []
        async for event in orch.run_stream(b"bad"):
            events.append(event)

        event_types = [e["event"] for e in events]
        assert "error" in event_types
        assert "result" not in event_types
        assert "done" not in event_types

    async def test_stream_agent_sequence(self, orchestrator: Orchestrator) -> None:
        """Agent done events should follow the correct order."""
        events = []
        async for event in orchestrator.run_stream(b"fake"):
            events.append(event)

        agent_done_stages = [
            json.loads(e["data"])["stage"]
            for e in events
            if e["event"] == "agent_done"
        ]
        assert agent_done_stages == ["vision", "styling", "recommendation", "shopping"]
