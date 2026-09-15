"""Embedding service — CLIP text/image embeddings for similarity ranking.

Reuses the vision module's process-wide CLIP model and inference pool, so
embedding a handful of product titles/thumbnails per request costs matrix
multiplies, not model loads.

Image-URL embeddings are cached in Redis (thumbnails are stable URLs and
CLIP is deterministic); text embeddings are cheap enough to compute inline.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from enum import Enum

import httpx
import torch

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.services.vision import (
    _CLOTHING_TYPE_PROMPTS,
    _COLOR_PROMPTS,
    _STYLE_PROMPTS,
    _classify_head,
    _encode_image,
    _get_models,
    _inference_pool,
    _open_image,
)

logger = get_logger(__name__)

_THUMB_CACHE_PREFIX = "emb:thumb:"
_THUMB_FETCH_TIMEOUT_S = 5.0

# Several image CDNs reject the default client user-agent outright (Wikimedia
# answers 403), which silently cost us every thumbnail from those hosts.
_THUMB_FETCH_HEADERS = {"User-Agent": "SynclookAI/1.0 (product thumbnail classifier)"}


class GenderLean(str, Enum):
    """Zero-shot gender lean of a product title."""

    MENSWEAR = "menswear"
    WOMENSWEAR = "womenswear"
    UNISEX = "unisex"


_GENDER_PROMPTS: dict[GenderLean, list[str]] = {
    GenderLean.MENSWEAR: ["men's clothing", "clothing for men"],
    GenderLean.WOMENSWEAR: ["women's clothing", "clothing for women"],
    GenderLean.UNISEX: ["unisex clothing", "clothing"],
}


def classify_embedding(embedding: list[float], head: str) -> tuple[str, float]:
    """Zero-shot classify an embedding against a catalog head.

    Works for text embeddings (product titles) exactly like the vision
    pipeline's image classification — same cached prompt features (one
    taxonomy, two modalities).
    """
    tensor = torch.tensor(embedding)
    holder = _get_models()
    if head == "clothing_type":
        return _classify_head(tensor, head, _CLOTHING_TYPE_PROMPTS, holder)
    if head == "color":
        return _classify_head(tensor, head, _COLOR_PROMPTS, holder)
    if head == "style":
        return _classify_head(tensor, head, _STYLE_PROMPTS, holder)
    if head == "gender":
        return _classify_head(tensor, head, _GENDER_PROMPTS, holder)
    raise ValueError(f"Unknown classification head: {head}")


def _embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Encode texts into normalized CLIP embeddings (runs in the vision pool)."""
    holder = _get_models()
    model, processor = holder.clip
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(holder.device) for k, v in inputs.items()}
    with torch.no_grad():
        features: torch.Tensor = model.get_text_features(**inputs).pooler_output
    features = features / features.norm(dim=-1, keepdim=True)
    return [row.tolist() for row in features]


def _embed_image_sync(image_bytes: bytes) -> list[float]:
    """Encode raw image bytes into a normalized CLIP embedding."""
    holder = _get_models()
    image = _open_image(image_bytes)
    return _encode_image(image, holder).tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two normalized embeddings (plain dot product)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


class EmbeddingService:
    """Async facade over CLIP for text and image-URL embeddings."""

    def __init__(self, redis_client=None) -> None:  # type: ignore[no-untyped-def]
        self._redis = redis_client
        self._settings = get_settings()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_inference_pool, _embed_texts_sync, texts)

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]

    async def embed_image_bytes(self, image_bytes: bytes) -> list[float]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_inference_pool, _embed_image_sync, image_bytes)

    async def embed_image_url(self, url: str) -> list[float] | None:
        """Fetch and embed an image URL; None on any failure (caller degrades).

        Results are cached in Redis keyed by URL hash — product thumbnails
        repeat heavily across requests thanks to the shopping cache.
        """
        if not url:
            return None

        cache_key = _THUMB_CACHE_PREFIX + hashlib.sha256(url.encode()).hexdigest()
        if self._redis is not None:
            try:
                cached = await self._redis.get(cache_key)
                if cached:
                    result: list[float] = json.loads(cached)
                    return result
            except Exception as exc:
                logger.warning("thumb_cache_read_failed", error=str(exc))

        try:
            async with httpx.AsyncClient(
                timeout=_THUMB_FETCH_TIMEOUT_S,
                follow_redirects=True,
                headers=_THUMB_FETCH_HEADERS,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                embedding = await self.embed_image_bytes(resp.content)
        except Exception as exc:
            logger.info("thumb_embed_failed", url=url[:80], error=str(exc))
            return None

        if self._redis is not None:
            try:
                await self._redis.set(
                    cache_key,
                    json.dumps(embedding),
                    ex=self._settings.shopping_cache_ttl_seconds,
                )
            except Exception as exc:
                logger.warning("thumb_cache_write_failed", error=str(exc))

        return embedding
