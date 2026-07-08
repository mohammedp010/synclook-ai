"""Shopping Agent — attaches real product links to recommendation items.

Iterates over RecommendationItems produced by the RecommendationAgent,
queries Google Shopping (via ProductSearchTool), and populates the
``products`` field with matching online products.

Product relevance ranking has two implementations selected by the
``shopping_matcher`` setting:

- ``embedding`` (default): CLIP similarity between the desired-item spec
  ("menswear navy shirt formal") and each product's title (plus thumbnail
  when fetchable) — one multimodal representation instead of hand-kept
  keyword/synonym tables
- ``keyword``: the legacy title-token matcher, retained so the offline
  relevance eval can compare both

Deterministic shopping-intent policy filtering always runs first in either
mode; ranking never overrides policy.
"""

from __future__ import annotations

import asyncio

from backend.agents.base import AgentContext, BaseAgent
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.schemas.api import ProductLink, Recommendation
from backend.services.embeddings import EmbeddingService, classify_embedding, cosine_similarity
from backend.tools.product_search import ProductSearchTool
from backend.tools.style_rules import (
    INVALID_ITEMS_BY_SHOPPING_INTENT,
    StyleRuleEngineTool,
    normalize_shopping_intent,
)

logger = get_logger(__name__)

MIN_PRODUCT_MATCH_SCORE = 0.5


class ShoppingAgent(BaseAgent):
    """Enriches recommendations with real product links from online stores.

    Skipped when ``ctx.include_products`` is False or when no
    ``ProductSearchTool`` is available.
    """

    name = "shopping"

    def __init__(
        self,
        product_tool: ProductSearchTool | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        super().__init__()
        self._tool = product_tool
        self._style_tool = StyleRuleEngineTool()
        self._settings = get_settings()
        self._embeddings = embedding_service

    def _post_filter_products(self, products: list[ProductLink], shopping_intent: str) -> list[ProductLink]:
        """Filter shopping results that violate deterministic shopping intent."""
        normalized_intent = normalize_shopping_intent(shopping_intent)
        invalid_items = INVALID_ITEMS_BY_SHOPPING_INTENT.get(normalized_intent, set())
        if not invalid_items:
            return products

        invalid_terms = {item.value for item in invalid_items}
        filtered = []
        for product in products:
            title = (getattr(product, "title", "") or "").lower()
            if any(term in title for term in invalid_terms):
                continue
            filtered.append(product)
        return filtered

    @staticmethod
    def _item_keywords(allowed_item_type: str) -> set[str]:
        allowed = (allowed_item_type or "").strip().lower().replace("_", "-")
        if not allowed:
            return set()

        synonyms = {
            "t-shirt": {"t-shirt", "tshirt", "tee"},
            "trousers": {"trousers", "pants"},
            "hoodie": {"hoodie", "hooded"},
            "shirt": {"shirt"},
            "blazer": {"blazer"},
            "jacket": {"jacket"},
            "sweater": {"sweater", "pullover"},
            "jeans": {"jeans", "denim"},
            "chinos": {"chinos"},
            "shorts": {"shorts"},
            "shoes": {"shoes", "sneakers", "footwear", "boots", "loafers"},
            "accessory": {"accessory", "belt", "watch", "bag", "scarf", "cap"},
        }
        return synonyms.get(allowed, {allowed})

    @staticmethod
    def _color_keywords(color: str) -> set[str]:
        normalized = (color or "").strip().lower()
        if not normalized:
            return set()
        synonyms = {
            "grey": {"grey", "gray"},
            "navy": {"navy", "dark blue"},
            "cream": {"cream", "off white", "off-white"},
        }
        return synonyms.get(normalized, {normalized})

    @staticmethod
    def _style_keywords(style: str) -> set[str]:
        normalized = (style or "").strip().lower().replace("_", " ")
        if not normalized:
            return set()
        return {normalized, *normalized.split()}

    def _score_product_match(
        self,
        product: ProductLink,
        *,
        allowed_item_type: str,
        color: str,
        style: str,
        shopping_intent: str,
    ) -> tuple[float, str]:
        title = (getattr(product, "title", "") or "").lower()
        if not title:
            return 0.0, "Missing product title"

        intent_filtered = self._post_filter_products([product], shopping_intent)
        if not intent_filtered:
            return 0.0, "Excluded by shopping intent"

        item_keywords = self._item_keywords(allowed_item_type)
        item_match = not item_keywords or any(token in title for token in item_keywords)
        if not item_match:
            return 0.0, "Item type does not match"

        score = 0.5
        reasons = [f"matches {allowed_item_type}"]

        color_keywords = self._color_keywords(color)
        if color_keywords and any(token in title for token in color_keywords):
            score += 0.15
            reasons.append(f"matches {color}")

        style_keywords = self._style_keywords(style)
        if style_keywords and any(token in title for token in style_keywords):
            score += 0.1
            reasons.append(f"matches {style.replace('_', ' ')}")

        if getattr(product, "thumbnail", ""):
            score += 0.1
            reasons.append("has image")

        price = (getattr(product, "price", "") or "").strip().lower()
        if price and price != "n/a":
            score += 0.1
            reasons.append("has price")

        if getattr(product, "source", ""):
            score += 0.05

        return min(round(score, 2), 1.0), "; ".join(reasons)

    def _validate_products_keyword(
        self,
        products: list[ProductLink],
        *,
        allowed_item_type: str,
        color: str,
        style: str,
        shopping_intent: str,
    ) -> list[ProductLink]:
        """Legacy keyword/synonym title matcher (kept for eval comparison)."""
        result = []
        for product in products:
            score, reason = self._score_product_match(
                product,
                allowed_item_type=allowed_item_type,
                color=color,
                style=style,
                shopping_intent=shopping_intent,
            )
            if score < MIN_PRODUCT_MATCH_SCORE:
                continue
            product.match_score = score
            product.match_reason = reason
            result.append(product)
        result.sort(key=lambda item: getattr(item, "match_score", 0.0), reverse=True)
        return result

    async def _validate_products_embedding(
        self,
        products: list[ProductLink],
        *,
        allowed_item_type: str,
        color: str,
        style: str,
        shopping_intent: str,
    ) -> list[ProductLink]:
        """Gate and rank products with zero-shot CLIP classification.

        Each title is embedded once, then classified against the same catalog
        heads the vision pipeline uses (one taxonomy, two modalities):

        - type gate: title must classify to the desired item type
        - color gate: title must classify to the desired color
        - gender gate: title must not classify to the opposite gender lean

        Survivors are ranked by similarity to the desired-item spec, blended
        with thumbnail image similarity when the thumbnail is fetchable.
        Calibrated on the labeled fixtures: F1 0.89 vs keyword's 0.84
        (precision 0.86 vs 0.74). Deterministic intent policy still runs
        first — ranking never overrides policy.
        """
        candidates = self._post_filter_products(products, shopping_intent)
        if not candidates:
            return []

        if self._embeddings is None:
            self._embeddings = EmbeddingService()

        normalized_intent = normalize_shopping_intent(shopping_intent)
        intent_prefix = {"menswear": "men's", "womenswear": "women's"}.get(normalized_intent, "")
        style_text = (style or "").replace("_", " ")
        spec = " ".join(part for part in (intent_prefix, color, allowed_item_type, style_text) if part)
        opposite_gender = {"menswear": "womenswear", "womenswear": "menswear"}.get(normalized_intent)

        spec_embedding, title_embeddings = await asyncio.gather(
            self._embeddings.embed_text(spec),
            self._embeddings.embed_texts([p.title for p in candidates]),
        )
        thumb_embeddings = await asyncio.gather(*(self._embeddings.embed_image_url(p.thumbnail) for p in candidates))

        threshold = self._settings.shopping_match_threshold
        result: list[ProductLink] = []
        for product, title_emb, thumb_emb in zip(candidates, title_embeddings, thumb_embeddings):
            predicted_type, _ = classify_embedding(title_emb, "clothing_type")
            if predicted_type != allowed_item_type:
                continue

            desired_color = (color or "").strip().lower()
            if desired_color:
                predicted_color, _ = classify_embedding(title_emb, "color")
                if predicted_color != desired_color:
                    continue

            if opposite_gender is not None:
                predicted_gender, _ = classify_embedding(title_emb, "gender")
                if predicted_gender == opposite_gender:
                    continue

            title_sim = cosine_similarity(spec_embedding, title_emb)
            if thumb_emb is not None:
                thumb_sim = cosine_similarity(spec_embedding, thumb_emb)
                score = 0.6 * title_sim + 0.4 * thumb_sim
                reason = f"zero-shot gates passed; similarity title {title_sim:.2f}, image {thumb_sim:.2f}"
            else:
                score = title_sim
                reason = f"zero-shot gates passed; similarity title {title_sim:.2f}"

            if score < threshold:
                continue
            product.match_score = round(min(max(score, 0.0), 1.0), 2)
            product.match_reason = reason
            result.append(product)

        result.sort(key=lambda item: getattr(item, "match_score", 0.0), reverse=True)
        return result

    async def _validate_products(
        self,
        products: list[ProductLink],
        *,
        allowed_item_type: str,
        color: str,
        style: str,
        shopping_intent: str,
    ) -> list[ProductLink]:
        if self._settings.shopping_matcher == "embedding":
            return await self._validate_products_embedding(
                products,
                allowed_item_type=allowed_item_type,
                color=color,
                style=style,
                shopping_intent=shopping_intent,
            )
        return self._validate_products_keyword(
            products,
            allowed_item_type=allowed_item_type,
            color=color,
            style=style,
            shopping_intent=shopping_intent,
        )

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        if not ctx.include_products:
            logger.info("shopping_skipped", reason="include_products=False")
            return ctx

        if self._tool is None:
            logger.info("shopping_skipped", reason="no product tool configured")
            return ctx

        if not ctx.recommendations:
            logger.info("shopping_skipped", reason="no recommendations")
            return ctx

        shopping_intent = normalize_shopping_intent(ctx.shopping_intent or ctx.gender)

        # Deduplicate queries: group items by (item_type, color, style)
        query_cache: dict[tuple[str, str, str], list[ProductLink]] = {}

        for rec in ctx.recommendations:
            if not isinstance(rec, Recommendation):
                continue
            for item in rec.items:
                if item.owned:
                    continue
                if not self._style_tool.is_item_allowed_for_gender(item.item_type, shopping_intent):
                    item.products = []
                    continue
                key = (item.item_type.lower(), item.color.lower(), item.style.lower())
                if key not in query_cache:
                    query_cache[key] = []

        # Fetch products for each unique query
        for item_type, color, style in query_cache:
            products = await self._tool.find_products(
                item_type=item_type,
                color=color,
                style=style,
                gender=ctx.gender,
                shopping_intent=shopping_intent,
            )
            query_cache[(item_type, color, style)] = products

        # Attach products to items
        total_products = 0
        for rec in ctx.recommendations:
            if not isinstance(rec, Recommendation):
                continue
            for item in rec.items:
                if item.owned:
                    item.products = []  # user already owns it — nothing to buy
                    continue
                if not self._style_tool.is_item_allowed_for_gender(item.item_type, shopping_intent):
                    item.products = []
                    continue
                key = (item.item_type.lower(), item.color.lower(), item.style.lower())
                item.products = await self._validate_products(
                    query_cache.get(key, []),
                    allowed_item_type=item.item_type,
                    color=item.color,
                    style=item.style,
                    shopping_intent=shopping_intent,
                )
                total_products += len(item.products)

        logger.info(
            "shopping_complete",
            unique_queries=len(query_cache),
            total_products=total_products,
        )

        return ctx
