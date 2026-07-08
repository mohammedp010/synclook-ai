"""Product search service — SerpAPI Google Shopping wrapper.

Queries Google Shopping via SerpAPI to find real products matching
recommendation items.  Results are cached in Redis to minimise API costs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.core.exceptions import ProductSearchError
from backend.core.logging import get_logger
from backend.schemas.api import ProductLink

logger = get_logger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


class ProductSearchService:
    """Async wrapper around SerpAPI Google Shopping."""

    _NEGATIVE_TOKENS = {
        "menswear": ["blouse", "women", "dress", "skirt", "ladies"],
        "womenswear": ["mens", "men"],
        "unisex": [],
        "all": [],
        # Legacy API values.
        "male": ["blouse", "women", "dress", "skirt", "ladies"],
        "female": ["mens", "men"],
    }

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.serpapi_api_key
        self._enabled = settings.shopping_enabled
        self._country = settings.shopping_country
        self._max_results = settings.shopping_results_per_item
        self._cache_ttl = settings.shopping_cache_ttl_seconds

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._api_key)

    @staticmethod
    def normalize_shopping_intent(value: str | None) -> str:
        normalized = (value or "unisex").strip().lower()
        legacy_map = {
            "male": "menswear",
            "men": "menswear",
            "mens": "menswear",
            "female": "womenswear",
            "women": "womenswear",
            "womens": "womenswear",
        }
        normalized = legacy_map.get(normalized, normalized)
        return normalized if normalized in {"menswear", "womenswear", "unisex", "all"} else "unisex"

    @staticmethod
    def build_query(item_type: str, color: str, style: str, shopping_intent: str) -> str:
        """Build a search query string from item attributes."""
        normalized_intent = ProductSearchService.normalize_shopping_intent(shopping_intent)
        prefix = {
            "menswear": "men",
            "womenswear": "women",
            "unisex": "unisex",
            "all": "",
        }.get(normalized_intent, "unisex")

        parts = [prefix, color.strip().lower(), item_type.strip().lower(), style.strip().lower()]
        base = " ".join(p for p in parts if p)

        negatives = ProductSearchService._NEGATIVE_TOKENS.get(normalized_intent, [])
        if negatives:
            base = f"{base} " + " ".join(f"-{token}" for token in negatives)
        return base.strip()

    @staticmethod
    def cache_key(query: str) -> str:
        """Deterministic Redis key for a normalised query."""
        normalised = query.strip().lower()
        digest = hashlib.sha256(normalised.encode()).hexdigest()[:16]
        return f"shopping:{digest}"

    async def search(self, query: str) -> list[ProductLink]:
        """Call SerpAPI Google Shopping and parse results.

        Returns up to ``self._max_results`` ProductLink objects.
        Raises ``ProductSearchError`` on HTTP or parsing failures.
        """
        if not self.enabled:
            return []

        params: dict[str, str | int] = {
            "engine": "google_shopping",
            "q": query,
            "api_key": self._api_key,
            "gl": self._country,
            "hl": "en",
            "num": self._max_results * 2,  # fetch extra so we can filter
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(SERPAPI_ENDPOINT, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("serpapi_http_error", status=exc.response.status_code, query=query)
            raise ProductSearchError(f"SerpAPI returned {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.error("serpapi_request_error", error=str(exc), query=query)
            raise ProductSearchError(f"SerpAPI request failed: {exc}") from exc

        return self._parse_results(data)

    def _parse_results(self, data: dict[str, Any]) -> list[ProductLink]:
        """Extract ProductLink objects from SerpAPI shopping_results."""
        products: list[ProductLink] = []

        for item in data.get("shopping_results", []):
            link = item.get("link") or item.get("product_link", "")
            thumbnail = item.get("thumbnail", "")
            title = item.get("title", "")
            price = item.get("extracted_price")
            source = item.get("source", "")

            if not link or not title:
                continue

            price_str = f"₹{price}" if price else item.get("price", "N/A")

            products.append(
                ProductLink(
                    title=title,
                    price=price_str,
                    link=link,
                    thumbnail=thumbnail,
                    source=source,
                )
            )

            if len(products) >= self._max_results:
                break

        return products

    @staticmethod
    def serialize(products: list[ProductLink]) -> str:
        """Serialize product list for Redis storage."""
        return json.dumps([p.model_dump() for p in products])

    @staticmethod
    def deserialize(raw: str) -> list[ProductLink]:
        """Deserialize product list from Redis."""
        return [ProductLink(**item) for item in json.loads(raw)]
