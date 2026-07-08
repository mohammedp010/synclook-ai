"""Wardrobe service — the user's digital closet.

Items are auto-tagged by the same vision pipeline as analysis uploads and
stored with their CLIP image embedding. Matching a recommendation item to the
wardrobe is tag-gated (category/type must agree — same taxonomy end to end)
and embedding-ranked (CLIP text-image similarity picks the best of several
candidates, e.g. which of three owned shirts suits "white shirt formal").

Retrieval is brute-force cosine in Python: a personal wardrobe is hundreds of
items at most, where a scan beats index round-trips. The scale-up path is a
pgvector column + HNSW index, deliberately not added prematurely.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.records import WardrobeItem
from backend.services.embeddings import EmbeddingService, cosine_similarity
from backend.services.vision import VisionService
from backend.tools.style_rules import StyleRuleEngineTool

logger = get_logger(__name__)

# CLIP text-image similarities are lower-scaled than text-text; this floor
# only breaks ties among tag-gated candidates, it is not the primary filter.
MIN_WARDROBE_SIMILARITY = 0.18


@dataclass
class WardrobeMatch:
    item: WardrobeItem
    similarity: float


class WardrobeService:
    """CRUD + matching for the user's digital closet."""

    def __init__(
        self,
        vision_service: VisionService,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._vision = vision_service
        self._embeddings = embedding_service or EmbeddingService()
        self._style_tool = StyleRuleEngineTool()

    async def add_item(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        image_bytes: bytes,
        label: str = "",
    ) -> WardrobeItem:
        """Auto-tag an uploaded garment photo and persist it."""
        result = await self._vision.analyze_image(image_bytes)
        attrs = result.attributes

        item = WardrobeItem(
            id=uuid.uuid4(),
            user_id=user_id,
            label=label,
            clothing_type=attrs.clothing_type.value,
            color=attrs.primary_color.value,
            pattern=attrs.pattern.value,
            style=attrs.style.value,
            embedding=result.image_embedding,
        )
        db.add(item)
        await db.flush()
        logger.info(
            "wardrobe_item_added",
            user_id=user_id,
            item_id=str(item.id),
            clothing_type=item.clothing_type,
            color=item.color,
        )
        return item

    async def list_items(self, db: AsyncSession, user_id: str) -> list[WardrobeItem]:
        rows = await db.execute(
            select(WardrobeItem).where(WardrobeItem.user_id == user_id).order_by(WardrobeItem.created_at.desc())
        )
        return list(rows.scalars().all())

    async def update_item(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        item_id: uuid.UUID,
        **fields: str,
    ) -> WardrobeItem | None:
        """Apply manual tag corrections (supervised feedback on the vision tags)."""
        row = await db.execute(select(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id))
        item = row.scalar_one_or_none()
        if item is None:
            return None
        allowed = {"label", "clothing_type", "color", "pattern", "style"}
        for key, value in fields.items():
            if key in allowed and value:
                setattr(item, key, value)
        await db.flush()
        logger.info("wardrobe_item_updated", user_id=user_id, item_id=str(item_id), fields=sorted(fields))
        return item

    async def delete_item(self, db: AsyncSession, *, user_id: str, item_id: uuid.UUID) -> bool:
        result = await db.execute(
            delete(WardrobeItem).where(WardrobeItem.id == item_id, WardrobeItem.user_id == user_id)
        )
        return bool(getattr(result, "rowcount", 0))

    # ── Matching ──────────────────────────────────────────────────────

    def rank_matches(
        self,
        items: list[WardrobeItem],
        *,
        item_type: str,
        color: str,
        style: str,
        spec_embedding: list[float],
    ) -> list[WardrobeMatch]:
        """Tag-gate then embedding-rank wardrobe items for a desired piece.

        Gate: same clothing type (taxonomy agreement beats fuzzy matching);
        color agreement is preferred but a same-type item in another color
        still qualifies at reduced similarity weight.
        """
        matches: list[WardrobeMatch] = []
        desired_color = (color or "").strip().lower()
        for item in items:
            if item.clothing_type != item_type:
                continue
            similarity = cosine_similarity(spec_embedding, item.embedding)
            if item.color != desired_color:
                similarity *= 0.85  # wearable, but not the requested color
            if similarity < MIN_WARDROBE_SIMILARITY:
                continue
            matches.append(WardrobeMatch(item=item, similarity=round(similarity, 4)))
        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches

    async def find_match(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        item_type: str,
        color: str,
        style: str,
    ) -> WardrobeMatch | None:
        """Best owned garment for a desired item spec, or None."""
        items = await self.list_items(db, user_id)
        if not items:
            return None
        style_text = (style or "").replace("_", " ")
        spec = " ".join(part for part in (color, item_type, style_text) if part)
        spec_embedding = await self._embeddings.embed_text(spec)
        ranked = self.rank_matches(
            items,
            item_type=item_type,
            color=color,
            style=style,
            spec_embedding=spec_embedding,
        )
        return ranked[0] if ranked else None
