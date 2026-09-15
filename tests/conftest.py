"""Shared test fixtures for Synclook."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.agents.base import AgentContext, StyleMatch
from backend.core.config import get_settings
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)
from backend.services.vision import VisionResult


@pytest.fixture(autouse=True)
def catalog_retrieval_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite hermetic — no test may depend on a live catalog.

    Catalog retrieval degrades gracefully when PostgreSQL is unreachable, so
    tests would pass either way; they would just pass slowly, for the wrong
    reason, and on a developer machine they would read whatever happens to be
    ingested. Tests that exercise retrieval turn it back on explicitly.
    """
    monkeypatch.setattr(get_settings(), "catalog_retrieval_enabled", False)


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
        return_value=VisionResult(
            attributes=ClothingAttributes(
                clothing_type=ClothingType.SHIRT,
                primary_color=Color.NAVY,
                pattern=Pattern.SOLID,
                style=Style.SMART_CASUAL,
                confidence=0.85,
                description="a navy blue dress shirt",
                description_relevant=True,
            ),
            image_embedding=[0.1] * 8,
        )
    )
    return svc
