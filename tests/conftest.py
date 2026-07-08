"""Shared test fixtures for Synclook."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.agents.base import AgentContext, StyleMatch
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)


@pytest.fixture
def sample_attributes() -> ClothingAttributes:
    """A realistic set of detected clothing attributes."""
    return ClothingAttributes(
        clothing_type=ClothingType.SHIRT,
        primary_color=Color.NAVY,
        pattern=Pattern.SOLID,
        style=Style.SMART_CASUAL,
        confidence=0.85,
        description="a navy blue dress shirt",
        description_relevant=True,
    )


@pytest.fixture
def sample_context(sample_attributes: ClothingAttributes) -> AgentContext:
    """An AgentContext pre-loaded with vision results (post-VisionAgent)."""
    ctx = AgentContext(image_bytes=b"fake-image-bytes", user_id="test-user")
    ctx.clothing_attributes = sample_attributes
    return ctx


@pytest.fixture
def sample_context_with_matches(sample_context: AgentContext) -> AgentContext:
    """An AgentContext pre-loaded with style matches (post-StylingAgent)."""
    sample_context.style_matches = [
        StyleMatch(
            item_type="trousers",
            recommended_colors=["white", "beige", "cream"],
            recommended_styles=["smart_casual", "formal"],
            match_score=0.85,
            rule_source="color_complement+style_compat+pattern",
        ),
        StyleMatch(
            item_type="blazer",
            recommended_colors=["white", "beige", "cream"],
            recommended_styles=["smart_casual", "formal"],
            match_score=0.85,
            rule_source="color_complement+style_compat+pattern",
        ),
        StyleMatch(
            item_type="shoes",
            recommended_colors=["black", "brown", "white"],
            recommended_styles=["smart_casual", "formal"],
            match_score=0.82,
            rule_source="color_complement+style_compat+pattern",
        ),
        StyleMatch(
            item_type="accessory",
            recommended_colors=["black", "brown", "white"],
            recommended_styles=["smart_casual", "formal"],
            match_score=0.78,
            rule_source="color_complement+style_compat+pattern",
        ),
    ]
    return sample_context


@pytest.fixture
def mock_vision_service() -> AsyncMock:
    """Mock VisionService that returns sample attributes without loading models."""
    svc = AsyncMock()
    svc.analyze_image = AsyncMock(
        return_value=ClothingAttributes(
            clothing_type=ClothingType.SHIRT,
            primary_color=Color.NAVY,
            pattern=Pattern.SOLID,
            style=Style.SMART_CASUAL,
            confidence=0.85,
            description="a navy blue dress shirt",
            description_relevant=True,
        )
    )
    return svc
