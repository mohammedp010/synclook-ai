"""Shopping Agent — attaches real product links to recommendation items.

Iterates over RecommendationItems produced by the RecommendationAgent,
queries Google Shopping (via ProductSearchTool), and populates the
``products`` field with matching online products.

Products come from two sources, in order:

1. **The local catalog** (:mod:`backend.services.product_catalog`) — hybrid
   lexical + vector retrieval over an ingested corpus, reranked by a
   cross-encoder. No network call, reproducible, and already normalized onto
   the project taxonomy at ingest time.
2. **Live provider search** — for slots the catalog cannot fill (it is
   deliberately narrow), the existing SerpAPI path runs and its results are
   gated by the zero-shot matcher below.

Product relevance ranking for the live path has two implementations selected
by the ``shopping_matcher`` setting:

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
from backend.agents.intent_agent import intent_from_context
from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.db.session import async_session_factory
from backend.schemas.api import ProductLink, Recommendation
from backend.services.embeddings import EmbeddingService, classify_embedding, cosine_similarity
from backend.services.product_catalog import CatalogQuery, ProductCatalogService
from backend.tools.product_search import ProductSearchTool
from backend.tools.style_rules import (
    INVALID_ITEMS_BY_SHOPPING_INTENT,
    StyleRuleEngineTool,
    normalize_shopping_intent,
)

logger = get_logger(__name__)

MIN_PRODUCT_MATCH_SCORE = 0.5

# Ranking nudge when the thumbnail classifies to the same garment as the title.
IMAGE_AGREEMENT_BONUS = 0.1
# A thumbnail may only veto a product when it is at least this confident.
IMAGE_VETO_MIN_CONFIDENCE = 0.5
# Upper bound on in-flight product-search calls per analysis.
MAX_CONCURRENT_PRODUCT_QUERIES = 6

# Catalog `gender_lean` values, keyed by normalized shopping intent.
_GENDER_LEAN_BY_INTENT = {"menswear": "men", "womenswear": "women"}


def build_item_spec(*, item_type: str, color: str, style: str, shopping_intent: str) -> str:
    """The canonical phrase describing a desired outfit slot.

    Both retrieval paths use it, so the catalog is searched with exactly the
    text the live matcher scores against — otherwise an A/B between them would
    be comparing queries as much as retrievers.
    """
    prefix = {"menswear": "men's", "womenswear": "women's"}.get(normalize_shopping_intent(shopping_intent), "")
    parts = (prefix, color, item_type, (style or "").replace("_", " "))
    return " ".join(part for part in parts if part)


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
        catalog: ProductCatalogService | None = None,
    ) -> None:
        super().__init__()
        self._tool = product_tool
        self._style_tool = StyleRuleEngineTool()
        self._settings = get_settings()
        self._embeddings = embedding_service
        self._catalog = catalog or ProductCatalogService()

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
    ) -> tuple[float, list[str]]:
        """Score a product, returning the facts that produced the score.

        The facts are returned as a list rather than a joined string so callers
        can surface them individually — same grounding contract as
        ``Recommendation.evidence``.
        """
        title = (getattr(product, "title", "") or "").lower()
        if not title:
            return 0.0, ["Missing product title"]

        intent_filtered = self._post_filter_products([product], shopping_intent)
        if not intent_filtered:
            return 0.0, ["Excluded by shopping intent"]

        item_keywords = self._item_keywords(allowed_item_type)
        item_match = not item_keywords or any(token in title for token in item_keywords)
        if not item_match:
            return 0.0, ["Item type does not match"]

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

        return min(round(score, 2), 1.0), reasons

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
            score, facts = self._score_product_match(
                product,
                allowed_item_type=allowed_item_type,
                color=color,
                style=style,
                shopping_intent=shopping_intent,
            )
            if score < MIN_PRODUCT_MATCH_SCORE:
                continue
            product.match_score = score
            product.match_reason = "; ".join(facts)
            product.match_evidence = facts
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

        Survivors are ranked by title similarity to the desired-item spec;
        a fetchable thumbnail can add a small ranking bonus when it agrees, or
        veto the product outright when it confidently shows a different garment.
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
        spec = build_item_spec(item_type=allowed_item_type, color=color, style=style, shopping_intent=shopping_intent)
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

            # Accept/reject on the text scale alone. ``title_sim`` is a text-text
            # cosine (~0.5-0.8 for real matches) whereas a text-image cosine sits
            # near 0.1-0.35 — CLIP never trained the two to share a scale. The
            # previous 0.6/0.4 blend was compared against a threshold calibrated
            # on text-only similarity, so it rejected every live product.
            title_sim = cosine_similarity(spec_embedding, title_emb)
            if title_sim < threshold:
                continue

            score = title_sim
            facts = ["zero-shot gates passed", f"title similarity {title_sim:.2f}"]

            if thumb_emb is not None:
                # Classify the thumbnail against the shared prompt set instead of
                # cosine-comparing it to the spec: a softmax probability *is*
                # comparable across modalities, a raw cross-modal cosine is not.
                thumb_type, thumb_conf = classify_embedding(thumb_emb, "clothing_type")
                if thumb_type == allowed_item_type:
                    score = min(1.0, score + IMAGE_AGREEMENT_BONUS * thumb_conf)
                    facts.append(f"thumbnail agrees ({thumb_conf:.2f})")
                elif thumb_conf >= IMAGE_VETO_MIN_CONFIDENCE:
                    # The picture confidently shows a different garment than the
                    # title claims — trust the picture and drop the product.
                    continue
                else:
                    facts.append("thumbnail inconclusive")

            product.match_score = round(min(max(score, 0.0), 1.0), 2)
            product.match_reason = "; ".join(facts)
            product.match_evidence = facts
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

    @staticmethod
    def _budget_inr(ctx: AgentContext) -> int | None:
        """The stated outfit budget, as a per-item ceiling.

        The intent budget covers the whole look, so it is a loose bound on any
        single product — but a loose bound still removes the ₹40,000 blazer
        from a ₹5,000 outfit before the verifier has to reject the result.
        """
        intent = intent_from_context(ctx)
        if intent is None or intent.budget_total_inr is None:
            return None
        return int(intent.budget_total_inr)

    async def _catalog_products(
        self,
        keys: list[tuple[str, str, str]],
        *,
        shopping_intent: str,
        budget_inr: int | None,
    ) -> dict[tuple[str, str, str], list[ProductLink]]:
        """Fill as many outfit slots as possible from the local corpus.

        Catalog hits skip the zero-shot gates the live path applies: those
        gates re-derive at request time what ingestion already established
        (see :mod:`backend.jobs.catalog_ingest`), and the cross-encoder score
        is a better relevance signal than title cosine anyway.

        Retrieval is best-effort. A missing table, an empty corpus or a failed
        model load all resolve to "no catalog results", which the caller reads
        as "ask the provider" — the same graceful degradation as every other
        optional dependency in the pipeline.
        """
        if not self._settings.catalog_retrieval_enabled or not keys:
            return {}

        limit = self._settings.shopping_results_per_item
        minimum = self._settings.catalog_min_score
        gender_lean = _GENDER_LEAN_BY_INTENT.get(normalize_shopping_intent(shopping_intent), "")

        found: dict[tuple[str, str, str], list[ProductLink]] = {}
        try:
            async with async_session_factory() as session:
                # Sequential by design: the cross-encoder is CPU-bound behind a
                # two-worker pool, so concurrent queries would queue anyway
                # while holding extra connections open.
                for key in keys:
                    item_type, color, style = key
                    query = CatalogQuery(
                        text=build_item_spec(
                            item_type=item_type, color=color, style=style, shopping_intent=shopping_intent
                        ),
                        clothing_type=item_type,
                        gender=gender_lean,
                        max_price_inr=budget_inr,
                    )
                    hits = await self._catalog.search(session, query, limit=limit)
                    products = [hit.to_product_link() for hit in hits if hit.score >= minimum]
                    if products:
                        found[key] = products
        except Exception as exc:
            logger.warning("catalog_retrieval_failed", error=str(exc))
            return {}

        logger.info("catalog_retrieval", slots=len(keys), slots_filled=len(found))
        return found

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

        # The catalog answers first: it costs no API credits and its rows were
        # already normalized onto the taxonomy at ingest.
        catalog_products = await self._catalog_products(
            list(query_cache),
            shopping_intent=shopping_intent,
            budget_inr=self._budget_inr(ctx),
        )

        # Only slots the catalog could not fill reach the provider. The queries
        # are independent, so they run concurrently — sequentially this was
        # ~8s x 12 queries. The semaphore keeps us from opening a dozen sockets
        # at the provider at once.
        unfilled = [key for key in query_cache if key not in catalog_products]
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PRODUCT_QUERIES)

        async def fetch(key: tuple[str, str, str]) -> tuple[tuple[str, str, str], list[ProductLink]]:
            item_type, color, style = key
            async with semaphore:
                assert self._tool is not None
                products = await self._tool.find_products(
                    item_type=item_type,
                    color=color,
                    style=style,
                    gender=ctx.gender,
                    shopping_intent=shopping_intent,
                )
            return key, products

        for key, products in await asyncio.gather(*(fetch(k) for k in unfilled)):
            query_cache[key] = products

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
                if key in catalog_products:
                    item.products = list(catalog_products[key])
                else:
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
            catalog_slots=len(catalog_products),
            provider_queries=len(unfilled),
            total_products=total_products,
        )

        return ctx
