"""Tests for ShoppingAgent and ProductSearchService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.agents.base import AgentContext, AgentState
from backend.agents.shopping_agent import ShoppingAgent
from backend.schemas.api import (
    ProductLink,
    Recommendation,
    RecommendationItem,
)
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
        assert "matches shirt" in matched.match_reason

    @pytest.mark.asyncio
    async def test_sorts_products_by_match_score(self):
        weaker = ProductLink(
            title="Shirt for men",
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
