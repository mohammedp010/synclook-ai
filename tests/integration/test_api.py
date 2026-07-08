"""API endpoint tests using httpx AsyncClient — no real server needed."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from PIL import Image

from backend.agents.base import AgentContext, StyleMatch
from backend.agents.orchestrator import Orchestrator
from backend.app import create_app
from backend.schemas.api import Recommendation, RecommendationItem
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


def _make_test_jpeg() -> bytes:
    """Generate a tiny valid JPEG in memory."""
    img = Image.new("RGB", (10, 10), color=(0, 0, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_completed_context() -> AgentContext:
    """Build a fully-populated context as if the orchestrator ran."""
    ctx = AgentContext(image_bytes=b"fake", user_id="test")
    ctx.clothing_attributes = ClothingAttributes(
        clothing_type=ClothingType.SHIRT,
        primary_color=Color.NAVY,
        pattern=Pattern.SOLID,
        style=Style.SMART_CASUAL,
        confidence=0.85,
        description="navy dress shirt",
    )
    ctx.style_matches = [
        StyleMatch("trousers", ["white"], ["smart_casual"], 0.9, "test"),
    ]
    ctx.recommendations = [
        Recommendation(
            items=[
                RecommendationItem(
                    item_type="trousers",
                    color="white",
                    style="smart_casual",
                    reason="Goes great with navy",
                ),
            ],
            overall_explanation="A sharp smart-casual outfit.",
            style_tags=["smart_casual"],
            confidence=0.9,
        ),
    ]
    ctx.metadata["total_elapsed_s"] = 0.5
    return ctx


@pytest.fixture
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock(spec=Orchestrator)
    orch.run = AsyncMock(return_value=_make_completed_context())

    async def _stream_gen(*args, **kwargs):
        import json
        yield {"event": "status", "data": json.dumps({"stage": "start", "message": "started"})}
        yield {"event": "done", "data": json.dumps({"elapsed_s": 0.1})}

    orch.run_stream = _stream_gen
    return orch


@pytest.fixture
def app(mock_orchestrator):
    """Create the FastAPI app with mocked dependencies."""
    from backend.core.dependencies import get_orchestrator, get_feedback_service
    from backend.db.session import get_db_session

    application = create_app()

    # Override dependencies
    application.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    application.dependency_overrides[get_db_session] = lambda: AsyncMock()
    application.dependency_overrides[get_feedback_service] = lambda: AsyncMock()

    return application


@pytest.fixture
async def client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestAnalyzeEndpoint:
    async def test_analyze_returns_200(self, client: AsyncClient) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
            params={"user_id": "test-api"},
        )
        assert resp.status_code == 200

    async def test_analyze_rejects_bad_content_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_analyze_response_has_request_id(self, client: AsyncClient) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
        )
        data = resp.json()
        assert "request_id" in data

    async def test_analyze_response_has_recommendations(self, client: AsyncClient) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
        )
        data = resp.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0

    async def test_analyze_unexpected_failure_returns_500(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        jpeg_bytes = _make_test_jpeg()
        mock_orchestrator.run.side_effect = RuntimeError("pipeline crash")

        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
        )

        assert resp.status_code == 500

    async def test_analyze_accepts_shopping_intent(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
            params={"shopping_intent": "menswear"},
        )

        assert resp.status_code == 200
        assert mock_orchestrator.run.call_args.kwargs["shopping_intent"] == "menswear"


class TestStreamEndpoint:
    async def test_stream_returns_200_sse(self, client: AsyncClient) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze/stream",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
            params={"user_id": "stream-test"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    async def test_stream_rejects_bad_content_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/analyze/stream",
            files={"image": ("test.gif", b"fake", "image/gif")},
        )
        assert resp.status_code == 400

    async def test_stream_contains_events(self, client: AsyncClient) -> None:
        jpeg_bytes = _make_test_jpeg()
        resp = await client.post(
            "/api/v1/analyze/stream",
            files={"image": ("test.jpg", jpeg_bytes, "image/jpeg")},
        )
        assert "event:" in resp.text
