"""Product search service — SerpAPI Google Shopping wrapper.

Queries Google Shopping via SerpAPI for one item the closet is missing.
``tools.product_search`` caches results in ``kv_cache`` for 7 days.
"""

from __future__ import annotations

import hashlib
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

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.serpapi_api_key
        self._enabled = settings.shopping_enabled
        self._country = settings.shopping_country
        self._max_results = settings.shopping_candidates_per_query
        self._cache_ttl = settings.shopping_cache_ttl_seconds

    @property
    def enabled(self) -> bool:
        """Shopping switched on. A missing key is an error at search time, not a silent off."""
        return self._enabled

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
        """Build a search query string from item attributes.

        No ``-women``-style exclusions: Google Shopping ignores the minus
        operator and reads the word as a keyword, so ``men black jeans
        -skirt -women`` came back as women's skirts and sarees (live run,
        2026-10-07). Wrong-buyer results are the product gate's job.
        """
        normalized_intent = ProductSearchService.normalize_shopping_intent(shopping_intent)
        prefix = {
            "menswear": "men",
            "womenswear": "women",
            "unisex": "unisex",
            "all": "",
        }.get(normalized_intent, "unisex")

        parts = [prefix, color.strip().lower(), item_type.strip().lower().replace("_", " "), style.strip().lower()]
        return " ".join(p for p in parts if p)

    @staticmethod
    def cache_key(query: str) -> str:
        """Deterministic cache key for a normalised query.

        Versioned: v2 entries hold the gate's candidate pool, v1 held only
        the two products shown, so a v1 entry must not be read as a pool.
        """
        normalised = query.strip().lower()
        digest = hashlib.sha256(normalised.encode()).hexdigest()[:16]
        return f"shopping:v2:{digest}"

    async def search(self, query: str, max_price: int | None = None) -> list[ProductLink]:
        """Call SerpAPI Google Shopping and parse results.

        Returns up to ``self._max_results`` ProductLink objects at or under *max_price* (₹).
        Raises ``ProductSearchError`` on HTTP or parsing failures.

        The budget is applied to the ~40 results in code, not sent as SerpAPI's
        ``max_price``: with ``gl=in`` that parameter made Google return nothing for
        "men white jacket" ≤ ₹3000, while 36 of the 40 unfiltered results were under
        it (live run, 2026-11-15).
        """
        if not self.enabled:
            return []
        if not self._api_key:
            raise ProductSearchError("SERPAPI_API_KEY is not set")

        params: dict[str, str | int] = {
            "engine": "google_shopping",
            "q": query,
            "api_key": self._api_key,
            "gl": self._country,
            "hl": "en",
            "num": self._max_results,
        }

        try:
            # 30s, not 15: uncached Google Shopping answers take 5-20s, and a
            # timed-out call is still billed. 4 of 11 timed out at 15s live.
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(SERPAPI_ENDPOINT, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("serpapi_http_error", status=exc.response.status_code, query=query)
            raise ProductSearchError(f"SerpAPI returned {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            # Transport failures frequently carry an empty ``str(exc)`` — a bare
            # ReadError or ConnectError says nothing — which made a real ingest
            # failure unreadable in the logs. The class name is the diagnosis.
            kind = type(exc).__name__
            logger.error("serpapi_request_error", error=str(exc) or "(no detail)", kind=kind, query=query)
            raise ProductSearchError(f"SerpAPI request failed ({kind}): {exc}") from exc

        return self._parse_results(data, max_price)

    def _parse_results(self, data: dict[str, Any], max_price: int | None = None) -> list[ProductLink]:
        """Extract ProductLink objects from SerpAPI shopping_results.

        The budget is applied here: a listing whose price is missing or over it is
        dropped, so the gate's pool holds only listings the shopper can afford.
        """
        products: list[ProductLink] = []
        seen_titles: set[str] = set()

        for item in data.get("shopping_results", []):
            link = item.get("link") or item.get("product_link", "")
            thumbnail = item.get("thumbnail", "")
            title = item.get("title", "")
            price = item.get("extracted_price")
            source = item.get("source", "")

            # Google lists one product once per seller; show it once.
            if not link or not title or title.lower() in seen_titles:
                continue
            if max_price is not None and not (isinstance(price, int | float) and price <= max_price):
                continue
            seen_titles.add(title.lower())

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
