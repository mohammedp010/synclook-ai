"""Product search tool — cache-aware wrapper around ProductSearchService.

Checks the kv_cache first; on miss calls SerpAPI and stores the result for 7 days.
"""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.schemas.api import ProductLink
from backend.services.cache import KvCache
from backend.services.product_search import ProductSearchService

logger = get_logger(__name__)


class ProductSearchTool:
    """Cache-first product lookup. Used by ``POST /shop/search``."""

    def __init__(
        self,
        search_service: ProductSearchService,
        cache: KvCache,
    ) -> None:
        self._search = search_service
        self._cache = cache

    def query(self, item_type: str, color: str, shopping_intent: str) -> str:
        return self._search.build_query(item_type, color, "", shopping_intent)

    async def find_products(
        self,
        item_type: str,
        color: str,
        shopping_intent: str,
        max_price: int | None = None,
    ) -> list[ProductLink]:
        """The candidate pool for one item, at or under *max_price* (₹).

        1. Build query from attributes.
        2. Check the cache (the budget is part of the key).
        3. On miss → call SerpAPI → store in cache.

        Raises ``ProductSearchError`` when SerpAPI fails, so the caller can say so.
        """
        query = self.query(item_type, color, shopping_intent)
        cache_key = self._search.cache_key(query if max_price is None else f"{query} | max ₹{max_price}")

        try:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("product_cache_hit", key=cache_key, query=query)
                return [ProductLink(**item) for item in cached]
        except Exception as exc:
            logger.warning("product_cache_read_error", error=str(exc))

        if not self._search.enabled:
            return []

        products = await self._search.search(query, max_price)

        if products:
            try:
                await self._cache.set(cache_key, [p.model_dump() for p in products], self._search._cache_ttl)
                logger.debug("product_cache_set", key=cache_key, count=len(products))
            except Exception as exc:
                logger.warning("product_cache_write_error", error=str(exc))

        logger.info("product_search_complete", query=query, max_price=max_price, count=len(products))
        return products
