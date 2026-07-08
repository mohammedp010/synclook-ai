"""Product search tool — cache-aware wrapper around ProductSearchService.

Checks Redis cache first; on miss calls SerpAPI and stores the result.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from backend.core.logging import get_logger
from backend.schemas.api import ProductLink
from backend.services.product_search import ProductSearchService

logger = get_logger(__name__)


class ProductSearchTool:
    """Cache-first product lookup.  Used by ``ShoppingAgent``."""

    def __init__(
        self,
        search_service: ProductSearchService,
        redis_client: aioredis.Redis,
    ) -> None:
        self._search = search_service
        self._redis = redis_client

    async def find_products(
        self,
        item_type: str,
        color: str,
        style: str,
        gender: str = "unisex",
        shopping_intent: str | None = None,
    ) -> list[ProductLink]:
        """Return product links for a recommendation item.

        1. Build query from attributes.
        2. Check Redis cache.
        3. On miss → call SerpAPI → store in cache.
        """
        query = self._search.build_query(item_type, color, style, shopping_intent or gender)
        cache_key = self._search.cache_key(query)

        # --- Cache hit ---
        try:
            cached = await self._redis.get(cache_key)
            if cached is not None:
                logger.debug("product_cache_hit", key=cache_key, query=query)
                return ProductSearchService.deserialize(cached)
        except Exception as exc:
            logger.warning("product_cache_read_error", error=str(exc))

        # --- Cache miss → API call ---
        if not self._search.enabled:
            return []

        try:
            products = await self._search.search(query)
        except Exception as exc:
            logger.warning("product_search_failed", query=query, error=str(exc))
            return []

        # --- Store in cache ---
        if products:
            try:
                await self._redis.set(
                    cache_key,
                    ProductSearchService.serialize(products),
                    ex=self._search._cache_ttl,
                )
                logger.debug("product_cache_set", key=cache_key, count=len(products))
            except Exception as exc:
                logger.warning("product_cache_write_error", error=str(exc))

        logger.info("product_search_complete", query=query, count=len(products))
        return products
