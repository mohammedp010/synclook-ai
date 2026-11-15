"""Unit tests for schemas."""

import pytest

from backend.schemas.api import HealthResponse
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


class TestHealthSchema:
    def test_health_response(self) -> None:
        resp = HealthResponse(version="0.1.0")
        assert resp.status == "healthy"
