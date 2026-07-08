"""Unit tests for schemas."""

from uuid import UUID

import pytest

from backend.schemas.api import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackType,
    HealthResponse,
    Recommendation,
    RecommendationItem,
)
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


class TestClothingAttributes:
    """Tests for ClothingAttributes Pydantic model."""

    def test_basic_construction(self) -> None:
        attrs = ClothingAttributes(
            clothing_type=ClothingType.SHIRT,
            primary_color=Color.NAVY,
            pattern=Pattern.SOLID,
            style=Style.FORMAL,
            confidence=0.9,
        )
        assert attrs.clothing_type == ClothingType.SHIRT
        assert attrs.secondary_color is None
        assert attrs.description == ""

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            ClothingAttributes(
                clothing_type=ClothingType.SHIRT,
                primary_color=Color.NAVY,
                pattern=Pattern.SOLID,
                style=Style.FORMAL,
                confidence=1.5,
            )

    def test_serialization_roundtrip(self) -> None:
        attrs = ClothingAttributes(
            clothing_type=ClothingType.JEANS,
            primary_color=Color.BLUE,
            pattern=Pattern.SOLID,
            style=Style.CASUAL,
            confidence=0.8,
            description="blue jeans",
        )
        data = attrs.model_dump(mode="json")
        restored = ClothingAttributes(**data)
        assert restored == attrs

    def test_all_clothing_types_valid(self) -> None:
        for ct in ClothingType:
            assert ct.value  # enum has a non-empty value

    def test_all_colors_valid(self) -> None:
        for c in Color:
            assert c.value

    def test_all_patterns_valid(self) -> None:
        for p in Pattern:
            assert p.value


class TestRecommendation:
    """Tests for Recommendation and RecommendationItem schemas."""

    def test_recommendation_item(self) -> None:
        item = RecommendationItem(
            item_type="jeans",
            color="black",
            style="casual",
            reason="Goes well with navy shirt",
        )
        assert item.item_type == "jeans"

    def test_recommendation(self) -> None:
        rec = Recommendation(
            items=[
                RecommendationItem(item_type="jeans", color="black", style="casual", reason="test"),
            ],
            overall_explanation="A great outfit",
            style_tags=["casual"],
            confidence=0.9,
        )
        assert len(rec.items) == 1
        assert isinstance(rec.id, UUID)

    def test_recommendation_json_roundtrip(self) -> None:
        rec = Recommendation(
            items=[
                RecommendationItem(item_type="jeans", color="black", style="casual", reason="test"),
            ],
            overall_explanation="A great outfit",
            style_tags=["casual"],
        )
        data = rec.model_dump(mode="json")
        restored = Recommendation(**data)
        assert restored.overall_explanation == rec.overall_explanation


class TestFeedbackSchemas:
    """Tests for feedback request/response schemas."""

    def test_feedback_request(self) -> None:
        req = FeedbackRequest(
            request_id="12345678-1234-1234-1234-123456789012",
            recommendation_id="12345678-1234-1234-1234-123456789012",
            feedback=FeedbackType.LIKE,
            user_id="user-1",
        )
        assert req.feedback == FeedbackType.LIKE

    def test_feedback_response_defaults(self) -> None:
        resp = FeedbackResponse()
        assert resp.status == "ok"
        assert resp.message == "Feedback recorded"

    def test_health_response(self) -> None:
        resp = HealthResponse(version="0.1.0")
        assert resp.status == "healthy"
