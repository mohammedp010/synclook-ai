"""Tests for wardrobe matching logic (pure functions — no DB required)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from backend.agents.base import AgentContext
from backend.agents.wardrobe_agent import WardrobeAgent
from backend.models.records import WardrobeItem
from backend.schemas.api import Recommendation, RecommendationItem
from backend.services.wardrobe import WardrobeMatch, WardrobeService


def _wardrobe_item(clothing_type: str, color: str, embedding: list[float]) -> WardrobeItem:
    return WardrobeItem(
        id=uuid.uuid4(),
        user_id="u1",
        label=f"my {color} {clothing_type}",
        clothing_type=clothing_type,
        color=color,
        pattern="solid",
        style="casual",
        embedding=embedding,
    )


def _service() -> WardrobeService:
    return WardrobeService(vision_service=MagicMock(), embedding_service=MagicMock())


class TestRankMatches:
    def test_type_gate_excludes_other_types(self) -> None:
        items = [
            _wardrobe_item("shirt", "white", [1.0, 0.0]),
            _wardrobe_item("jeans", "white", [1.0, 0.0]),
        ]
        matches = _service().rank_matches(
            items, item_type="shirt", color="white", style="casual", spec_embedding=[1.0, 0.0]
        )
        assert [m.item.clothing_type for m in matches] == ["shirt"]

    def test_color_mismatch_is_penalized_not_excluded(self) -> None:
        items = [
            _wardrobe_item("shirt", "white", [1.0, 0.0]),
            _wardrobe_item("shirt", "black", [1.0, 0.0]),
        ]
        matches = _service().rank_matches(
            items, item_type="shirt", color="white", style="casual", spec_embedding=[1.0, 0.0]
        )
        assert len(matches) == 2
        assert matches[0].item.color == "white"
        assert matches[0].similarity > matches[1].similarity

    def test_low_similarity_excluded(self) -> None:
        items = [_wardrobe_item("shirt", "white", [0.0, 1.0])]  # orthogonal to spec
        matches = _service().rank_matches(
            items, item_type="shirt", color="white", style="casual", spec_embedding=[1.0, 0.0]
        )
        assert matches == []


class TestWardrobeAgent:
    async def test_marks_matched_items_owned(self, monkeypatch) -> None:
        service = MagicMock()
        owned_item = _wardrobe_item("shirt", "white", [1.0, 0.0])
        service.find_match = AsyncMock(return_value=WardrobeMatch(item=owned_item, similarity=0.31))

        class _FakeSession:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *args):
                return None

        monkeypatch.setattr("backend.agents.wardrobe_agent.async_session_factory", lambda: _FakeSession())

        ctx = AgentContext(image_bytes=b"x", user_id="u1")
        ctx.recommendations = [
            Recommendation(
                id=uuid.uuid4(),
                items=[RecommendationItem(item_type="shirt", color="white", style="casual", reason="r")],
                overall_explanation="e",
            )
        ]
        ctx = await WardrobeAgent(service).run(ctx)

        item = ctx.recommendations[0].items[0]
        assert item.owned is True
        assert item.wardrobe_item_id == str(owned_item.id)
        assert ctx.metadata["wardrobe_matches"] == 1

    async def test_skips_without_user(self) -> None:
        service = MagicMock()
        ctx = AgentContext(image_bytes=b"x", user_id=None)
        ctx = await WardrobeAgent(service).run(ctx)
        service.find_match.assert_not_called()
