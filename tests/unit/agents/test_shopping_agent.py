"""Tests for ShoppingAgent and ProductSearchService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.agents.base import AgentContext, AgentState
from backend.agents.shopping_agent import ShoppingAgent
from backend.core.config import get_settings
from backend.models.records import ProductCatalogItem
from backend.schemas.api import (
    ProductLink,
    Recommendation,
    RecommendationItem,
)
from backend.services.product_catalog import CatalogHit, CatalogQuery
from backend.services.product_search import ProductSearchService
from backend.tools.product_search import ProductSearchTool

# ── Fixtures ──────────────────────────────────────────────────────────


def _sample_product(n: int = 1, title: str = "Test Product") -> ProductLink:
    return ProductLink(
        title=f"{title} {n}",
        price="₹999",
        link=f"https://example.com/product-{n}",
        thumbnail=f"https://example.com/img-{n}.jpg",
        source="Amazon.in",
    )


def _sample_recommendation() -> Recommendation:
    return Recommendation(
        id=uuid4(),
        items=[
            RecommendationItem(
                item_type="shirt",
                color="white",
                style="smart_casual",
                reason="pairs well",
            ),
            RecommendationItem(
                item_type="blazer",
                color="navy",
                style="formal",
                reason="complement",
            ),
        ],
        overall_explanation="A great outfit",
        style_tags=["smart_casual"],
        confidence=0.85,
    )


@pytest.fixture
def mock_product_tool() -> AsyncMock:
    tool = AsyncMock(spec=ProductSearchTool)
    tool.find_products = AsyncMock(
        return_value=[
            _sample_product(1, title="White shirt for men"),
            _sample_product(2, title="Navy blazer for men"),
        ]
    )
    return tool


@pytest.fixture
def ctx_with_recommendations() -> AgentContext:
    ctx = AgentContext(image_bytes=b"fake", user_id="u1")
    ctx.recommendations = [_sample_recommendation()]
    return ctx


# ── ProductSearchService tests ────────────────────────────────────────


class TestProductSearchService:
    def test_build_query_with_gender(self):
        q = ProductSearchService.build_query("chinos", "navy", "casual", "male")
        assert q.startswith("men navy chinos casual")
        assert "-blouse" in q
        assert "-women" in q

    def test_build_query_with_menswear_intent(self):
        q = ProductSearchService.build_query("chinos", "navy", "casual", "menswear")
        assert q.startswith("men navy chinos casual")
        assert "-blouse" in q
        assert "-women" in q

    def test_build_query_all_intent_has_no_prefix_or_negative_tokens(self):
        q = ProductSearchService.build_query("trousers", "white", "formal", "all")
        assert q == "white trousers formal"

    def test_build_query_unisex(self):
        q = ProductSearchService.build_query("trousers", "white", "formal", "unisex")
        assert q == "unisex white trousers formal"

    def test_cache_key_deterministic(self):
        k1 = ProductSearchService.cache_key("navy casual chinos")
        k2 = ProductSearchService.cache_key("navy casual chinos")
        assert k1 == k2
        assert k1.startswith("shopping:")

    def test_cache_key_case_insensitive(self):
        k1 = ProductSearchService.cache_key("Navy Casual Chinos")
        k2 = ProductSearchService.cache_key("navy casual chinos")
        assert k1 == k2

    def test_cache_key_different_queries(self):
        k1 = ProductSearchService.cache_key("navy chinos")
        k2 = ProductSearchService.cache_key("white trousers")
        assert k1 != k2

    def test_enabled_without_key(self):
        with patch.object(ProductSearchService, "__init__", lambda self: None):
            svc = ProductSearchService.__new__(ProductSearchService)
            svc._api_key = ""
            svc._enabled = True
            assert svc.enabled is False

    def test_enabled_with_key(self):
        with patch.object(ProductSearchService, "__init__", lambda self: None):
            svc = ProductSearchService.__new__(ProductSearchService)
            svc._api_key = "test-key"
            svc._enabled = True
            assert svc.enabled is True

    def test_enabled_flag_off_overrides_key(self):
        with patch.object(ProductSearchService, "__init__", lambda self: None):
            svc = ProductSearchService.__new__(ProductSearchService)
            svc._api_key = "test-key"
            svc._enabled = False
            assert svc.enabled is False

    def test_serialize_deserialize_roundtrip(self):
        products = [_sample_product(1), _sample_product(2)]
        raw = ProductSearchService.serialize(products)
        restored = ProductSearchService.deserialize(raw)
        assert len(restored) == 2
        assert restored[0].title == "Test Product 1"
        assert restored[1].link == "https://example.com/product-2"

    def test_parse_results(self):
        with patch.object(ProductSearchService, "__init__", lambda self: None):
            svc = ProductSearchService.__new__(ProductSearchService)
            svc._max_results = 2
            data = {
                "shopping_results": [
                    {
                        "title": "Navy Chinos",
                        "link": "https://amazon.in/chinos",
                        "thumbnail": "https://amazon.in/img.jpg",
                        "extracted_price": 1299,
                        "source": "Amazon.in",
                    },
                    {
                        "title": "Blue Pants",
                        "link": "https://myntra.com/pants",
                        "thumbnail": "https://myntra.com/img.jpg",
                        "price": "₹999",
                        "source": "Myntra",
                    },
                ]
            }
            results = svc._parse_results(data)
            assert len(results) == 2
            assert results[0].price == "₹1299"
            assert results[1].source == "Myntra"

    def test_parse_results_skips_incomplete(self):
        with patch.object(ProductSearchService, "__init__", lambda self: None):
            svc = ProductSearchService.__new__(ProductSearchService)
            svc._max_results = 5
            data = {
                "shopping_results": [
                    {"title": "", "link": ""},  # skip: no title
                    {"title": "Good", "link": ""},  # skip: no link
                    {
                        "title": "Valid",
                        "link": "https://example.com",
                        "thumbnail": "",
                        "source": "Store",
                    },
                ]
            }
            results = svc._parse_results(data)
            assert len(results) == 1
            assert results[0].title == "Valid"


# ── ProductSearchTool tests ───────────────────────────────────────────


class TestProductSearchTool:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        svc = MagicMock(spec=ProductSearchService)
        svc.build_query.return_value = "white formal trousers"
        svc.cache_key.return_value = "shopping:abc123"
        svc.enabled = True

        products = [_sample_product(1)]
        cached_data = ProductSearchService.serialize(products)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=cached_data)

        tool = ProductSearchTool(svc, redis)
        result = await tool.find_products("trousers", "white", "formal")

        assert len(result) == 1
        assert result[0].title == "Test Product 1"
        svc.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self):
        svc = MagicMock(spec=ProductSearchService)
        svc.build_query.return_value = "white formal trousers"
        svc.cache_key.return_value = "shopping:abc123"
        svc.enabled = True
        svc._cache_ttl = 604800

        products = [_sample_product(1)]
        svc.search = AsyncMock(return_value=products)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        tool = ProductSearchTool(svc, redis)
        result = await tool.find_products("trousers", "white", "formal")

        assert len(result) == 1
        svc.search.assert_awaited_once_with("white formal trousers")
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disabled_service_returns_empty(self):
        svc = MagicMock(spec=ProductSearchService)
        svc.build_query.return_value = "query"
        svc.cache_key.return_value = "shopping:x"
        svc.enabled = False

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        tool = ProductSearchTool(svc, redis)
        result = await tool.find_products("trousers", "white", "formal")
        assert result == []

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self):
        svc = MagicMock(spec=ProductSearchService)
        svc.build_query.return_value = "query"
        svc.cache_key.return_value = "shopping:x"
        svc.enabled = True
        svc.search = AsyncMock(side_effect=Exception("API down"))

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        tool = ProductSearchTool(svc, redis)
        result = await tool.find_products("trousers", "white", "formal")
        assert result == []


# ── ShoppingAgent tests ──────────────────────────────────────────────


class TestShoppingAgent:
    @pytest.mark.asyncio
    async def test_attaches_products(self, mock_product_tool, ctx_with_recommendations):
        agent = ShoppingAgent(product_tool=mock_product_tool)
        ctx = await agent.run(ctx_with_recommendations)

        assert agent.state == AgentState.DONE
        for rec in ctx.recommendations:
            for item in rec.items:
                assert len(item.products) >= 1

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, mock_product_tool, ctx_with_recommendations):
        ctx_with_recommendations.include_products = False
        agent = ShoppingAgent(product_tool=mock_product_tool)
        ctx = await agent.run(ctx_with_recommendations)

        assert agent.state == AgentState.DONE
        for rec in ctx.recommendations:
            for item in rec.items:
                assert item.products == []
        mock_product_tool.find_products.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_tool(self, ctx_with_recommendations):
        agent = ShoppingAgent(product_tool=None)
        await agent.run(ctx_with_recommendations)
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_skips_when_no_recommendations(self, mock_product_tool):
        ctx = AgentContext(image_bytes=b"fake")
        agent = ShoppingAgent(product_tool=mock_product_tool)
        result = await agent.run(ctx)
        assert result.recommendations == []
        mock_product_tool.find_products.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_queries(self, mock_product_tool):
        """Items with same type+color+style should result in one API call."""
        mock_product_tool.find_products = AsyncMock(return_value=[_sample_product(1, title="White trousers for men")])
        rec = Recommendation(
            id=uuid4(),
            items=[
                RecommendationItem(item_type="trousers", color="white", style="casual", reason="r1"),
                RecommendationItem(item_type="trousers", color="white", style="casual", reason="r2"),
            ],
            overall_explanation="test",
            style_tags=[],
            confidence=0.8,
        )
        ctx = AgentContext(image_bytes=b"fake")
        ctx.recommendations = [rec]

        agent = ShoppingAgent(product_tool=mock_product_tool)
        await agent.run(ctx)

        # Only 1 unique query despite 2 items with same attributes
        mock_product_tool.find_products.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_gender(self, mock_product_tool, ctx_with_recommendations):
        ctx_with_recommendations.gender = "male"
        agent = ShoppingAgent(product_tool=mock_product_tool)
        await agent.run(ctx_with_recommendations)

        for call in mock_product_tool.find_products.call_args_list:
            assert call.kwargs.get("gender") == "male" or call[1].get("gender") == "male"

    @pytest.mark.asyncio
    async def test_passes_shopping_intent(self, mock_product_tool, ctx_with_recommendations):
        ctx_with_recommendations.gender = "unisex"
        ctx_with_recommendations.shopping_intent = "menswear"
        agent = ShoppingAgent(product_tool=mock_product_tool)
        await agent.run(ctx_with_recommendations)

        for call in mock_product_tool.find_products.call_args_list:
            assert call.kwargs.get("shopping_intent") == "menswear"

    @pytest.mark.asyncio
    async def test_timing_recorded(self, mock_product_tool, ctx_with_recommendations):
        agent = ShoppingAgent(product_tool=mock_product_tool)
        ctx = await agent.run(ctx_with_recommendations)
        assert "shopping" in ctx.agent_timings

    @pytest.mark.asyncio
    async def test_post_filter_removes_gender_invalid_titles(self):
        bad = ProductLink(
            title="White blouse for women",
            price="₹1299",
            link="https://example.com/bad",
            thumbnail="https://example.com/bad.jpg",
            source="Store",
        )
        good = ProductLink(
            title="White streetwear shirt for men",
            price="₹999",
            link="https://example.com/good",
            thumbnail="https://example.com/good.jpg",
            source="Store",
        )

        tool = AsyncMock(spec=ProductSearchTool)
        tool.find_products = AsyncMock(return_value=[bad, good])

        rec = Recommendation(
            id=uuid4(),
            items=[
                RecommendationItem(
                    item_type="shirt",
                    color="white",
                    style="streetwear",
                    reason="test",
                )
            ],
            overall_explanation="test",
            style_tags=[],
            confidence=0.8,
        )
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.recommendations = [rec]

        agent = ShoppingAgent(product_tool=tool)
        result = await agent.run(ctx)

        products = result.recommendations[0].items[0].products
        assert len(products) == 1
        assert "blouse" not in products[0].title.lower()

    @pytest.mark.asyncio
    async def test_post_filter_removes_wrong_item_type_titles(self):
        wrong = ProductLink(
            title="Red womens dress",
            price="₹1299",
            link="https://example.com/wrong",
            thumbnail="https://example.com/wrong.jpg",
            source="Store",
        )
        correct = ProductLink(
            title="Red formal shirt for men",
            price="₹999",
            link="https://example.com/correct",
            thumbnail="https://example.com/correct.jpg",
            source="Store",
        )

        tool = AsyncMock(spec=ProductSearchTool)
        tool.find_products = AsyncMock(return_value=[wrong, correct])

        rec = Recommendation(
            id=uuid4(),
            items=[
                RecommendationItem(
                    item_type="shirt",
                    color="red",
                    style="formal",
                    reason="test",
                )
            ],
            overall_explanation="test",
            style_tags=[],
            confidence=0.8,
        )
        ctx = AgentContext(image_bytes=b"fake", gender="male")
        ctx.recommendations = [rec]

        agent = ShoppingAgent(product_tool=tool)
        result = await agent.run(ctx)

        products = result.recommendations[0].items[0].products
        assert len(products) == 1
        assert "shirt" in products[0].title.lower()

    @pytest.mark.asyncio
    async def test_adds_product_match_metadata(self):
        product = ProductLink(
            title="White smart casual shirt for men",
            price="₹999",
            link="https://example.com/shirt",
            thumbnail="https://example.com/shirt.jpg",
            source="Store",
        )

        tool = AsyncMock(spec=ProductSearchTool)
        tool.find_products = AsyncMock(return_value=[product])

        rec = Recommendation(
            id=uuid4(),
            items=[
                RecommendationItem(
                    item_type="shirt",
                    color="white",
                    style="smart_casual",
                    reason="test",
                )
            ],
            overall_explanation="test",
            style_tags=[],
            confidence=0.8,
        )
        ctx = AgentContext(image_bytes=b"fake", shopping_intent="menswear")
        ctx.recommendations = [rec]

        agent = ShoppingAgent(product_tool=tool)
        result = await agent.run(ctx)

        matched = result.recommendations[0].items[0].products[0]
        assert matched.match_score > 0.5
        assert matched.match_reason  # human-readable evidence for the match

    @pytest.mark.asyncio
    async def test_sorts_products_by_match_score(self):
        weaker = ProductLink(
            title="White shirt",
            price="₹999",
            link="https://example.com/weaker",
            thumbnail="",
            source="Store",
        )
        stronger = ProductLink(
            title="White smart casual shirt for men",
            price="₹999",
            link="https://example.com/stronger",
            thumbnail="https://example.com/stronger.jpg",
            source="Store",
        )

        tool = AsyncMock(spec=ProductSearchTool)
        tool.find_products = AsyncMock(return_value=[weaker, stronger])

        rec = Recommendation(
            id=uuid4(),
            items=[
                RecommendationItem(
                    item_type="shirt",
                    color="white",
                    style="smart_casual",
                    reason="test",
                )
            ],
            overall_explanation="test",
            style_tags=[],
            confidence=0.8,
        )
        ctx = AgentContext(image_bytes=b"fake", shopping_intent="menswear")
        ctx.recommendations = [rec]

        agent = ShoppingAgent(product_tool=tool)
        result = await agent.run(ctx)

        products = result.recommendations[0].items[0].products
        assert products[0].link == "https://example.com/stronger"
        assert products[0].match_score > products[1].match_score


class TestThumbnailGating:
    """Covers the thumbnail branch of the embedding matcher.

    Regression guard for a live-only failure: the matcher used to blend a
    text-text cosine with a text-image cosine and compare the mix against a
    threshold calibrated on text alone, which rejected 100% of real products.
    Every existing fixture used an unfetchable thumbnail, so the blended branch
    never ran and the offline eval stayed green while production returned zero.
    """

    SPEC = [1.0, 0.0, 0.0]
    TITLE = [0.8, 0.6, 0.0]  # unit vector; cosine vs SPEC = 0.80, above the 0.75 gate
    THUMB = [0.0, 0.0, 1.0]  # orthogonal to SPEC: cosine-comparing it would score 0.0

    def _agent(self):
        embeddings = MagicMock()
        embeddings.embed_text = AsyncMock(return_value=self.SPEC)
        embeddings.embed_texts = AsyncMock(return_value=[self.TITLE])
        embeddings.embed_image_url = AsyncMock(return_value=self.THUMB)
        return ShoppingAgent(product_tool=None, embedding_service=embeddings)

    @staticmethod
    def _product():
        return ProductLink(
            title="White smart casual shirt for men",
            price="₹999",
            link="https://example.com/shirt",
            thumbnail="https://cdn.example.com/real-thumb.jpg",
            source="Store",
        )

    def _classifier(self, thumb_result):
        """Fake zero-shot heads: titles always match, thumbnails are scripted."""

        def fake(embedding, head):
            if embedding == self.THUMB:
                return thumb_result
            return {"clothing_type": ("shirt", 0.9), "color": ("white", 0.9), "gender": ("menswear", 0.9)}[head]

        return fake

    async def _validate(self, thumb_result):
        agent = self._agent()
        with patch("backend.agents.shopping_agent.classify_embedding", self._classifier(thumb_result)):
            return await agent._validate_products_embedding(
                [self._product()],
                allowed_item_type="shirt",
                color="white",
                style="smart_casual",
                shopping_intent="menswear",
            )

    @pytest.mark.asyncio
    async def test_fetchable_thumbnail_does_not_reject_a_good_product(self):
        kept = await self._validate(("shirt", 0.8))

        assert len(kept) == 1, "a fetchable thumbnail must not sink a product that passed every gate"
        assert kept[0].match_score >= 0.8  # stays on the text scale, plus the agreement bonus
        assert "thumbnail agrees" in kept[0].match_reason

    @pytest.mark.asyncio
    async def test_confident_thumbnail_disagreement_vetoes_the_product(self):
        assert await self._validate(("shoes", 0.9)) == []

    @pytest.mark.asyncio
    async def test_unsure_thumbnail_disagreement_is_ignored(self):
        kept = await self._validate(("shoes", 0.2))

        assert len(kept) == 1
        assert "thumbnail inconclusive" in kept[0].match_reason


class _StubCatalog:
    """Stands in for ProductCatalogService without a database or models."""

    def __init__(self, hits_by_type: dict[str, list[CatalogHit]]) -> None:
        self.hits_by_type = hits_by_type
        self.queries: list[CatalogQuery] = []

    async def search(self, db: object, query: CatalogQuery, *, limit: int) -> list[CatalogHit]:
        self.queries.append(query)
        return self.hits_by_type.get(query.clothing_type, [])[:limit]


def _catalog_hit(title: str, score: float) -> CatalogHit:
    item = ProductCatalogItem(
        title=title,
        price_display="₹2,499",
        product_url=f"https://example.test/{title}",
        thumbnail_url="",
        store="Myntra",
        source="fixture",
    )
    return CatalogHit(
        item=item,
        score=score,
        reason="hybrid retrieval",
        evidence=("Keyword search ranked it #1", "Cross-encoder relevance 0.97"),
    )


class TestCatalogRetrieval:
    """The catalog answers before the provider does."""

    @staticmethod
    def _agent(catalog: _StubCatalog, monkeypatch: pytest.MonkeyPatch) -> ShoppingAgent:
        monkeypatch.setattr(get_settings(), "catalog_retrieval_enabled", True)
        return ShoppingAgent(product_tool=MagicMock(), catalog=catalog)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_confident_hits_fill_the_slot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        catalog = _StubCatalog({"blazer": [_catalog_hit("Navy Formal Blazer", 0.97)]})
        agent = self._agent(catalog, monkeypatch)

        found = await agent._catalog_products(
            [("blazer", "navy", "formal")], shopping_intent="menswear", budget_inr=None
        )

        assert [p.title for p in found[("blazer", "navy", "formal")]] == ["Navy Formal Blazer"]

    @pytest.mark.asyncio
    async def test_retrieval_provenance_reaches_the_product(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Why a product was retrieved is as much a grounded fact as why an item
        # was recommended — it has to survive the hop into the API schema.
        catalog = _StubCatalog({"blazer": [_catalog_hit("Navy Formal Blazer", 0.97)]})
        agent = self._agent(catalog, monkeypatch)

        found = await agent._catalog_products(
            [("blazer", "navy", "formal")], shopping_intent="menswear", budget_inr=None
        )

        product = found[("blazer", "navy", "formal")][0]
        assert product.match_evidence == ["Keyword search ranked it #1", "Cross-encoder relevance 0.97"]
        assert product.match_score == 0.97

    @pytest.mark.asyncio
    async def test_low_scoring_hits_leave_the_slot_for_the_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Below `catalog_min_score` the corpus has nothing worth showing; the
        # slot must stay unfilled so live search still runs for it.
        catalog = _StubCatalog({"blazer": [_catalog_hit("Beige Linen Blazer", 0.11)]})
        agent = self._agent(catalog, monkeypatch)

        found = await agent._catalog_products(
            [("blazer", "navy", "formal")], shopping_intent="menswear", budget_inr=None
        )

        assert found == {}

    @pytest.mark.asyncio
    async def test_query_carries_the_slot_constraints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        catalog = _StubCatalog({})
        agent = self._agent(catalog, monkeypatch)

        await agent._catalog_products([("blazer", "navy", "formal")], shopping_intent="menswear", budget_inr=5000)

        query = catalog.queries[0]
        assert query.text == "men's navy blazer formal"
        assert query.clothing_type == "blazer"
        assert query.gender == "men"
        assert query.max_price_inr == 5000

    @pytest.mark.asyncio
    async def test_disabled_retrieval_asks_no_questions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        catalog = _StubCatalog({"blazer": [_catalog_hit("Navy Formal Blazer", 0.97)]})
        monkeypatch.setattr(get_settings(), "catalog_retrieval_enabled", False)
        agent = ShoppingAgent(product_tool=MagicMock(), catalog=catalog)  # type: ignore[arg-type]

        found = await agent._catalog_products(
            [("blazer", "navy", "formal")], shopping_intent="menswear", budget_inr=None
        )

        assert found == {}
        assert catalog.queries == []
