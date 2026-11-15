"""SerpAPI search (query, budget, parsing), its kv_cache wrapper, and the product gate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.exceptions import ProductSearchError
from backend.schemas.api import ProductLink
from backend.services.jev import JevUnavailableError
from backend.services.product_judge import ProductVerdict, Wanted, gate
from backend.services.product_search import ProductSearchService
from backend.tools.product_search import ProductSearchTool


def _product(n: int = 1, title: str = "Test Product") -> ProductLink:
    return ProductLink(
        title=f"{title} {n}",
        price="₹999",
        link=f"https://example.com/product-{n}",
        thumbnail=f"https://example.com/img-{n}.jpg",
        source="Amazon.in",
    )


def _service(max_results: int = 5) -> ProductSearchService:
    with patch.object(ProductSearchService, "__init__", lambda self: None):
        svc = ProductSearchService.__new__(ProductSearchService)
    svc._max_results = max_results
    svc._api_key = "test-key"
    svc._enabled = True
    svc._country = "in"
    return svc


class TestProductSearchService:
    def test_build_query_with_gender(self) -> None:
        assert ProductSearchService.build_query("chinos", "navy", "casual", "male") == "men navy chinos casual"

    def test_build_query_has_no_minus_exclusions(self) -> None:
        # Google Shopping reads "-women" as the keyword "women".
        q = ProductSearchService.build_query("jeans", "black", "", "menswear")
        assert q == "men black jeans" and "-" not in q

    def test_build_query_all_intent_has_no_prefix(self) -> None:
        assert ProductSearchService.build_query("t_shirt", "white", "", "all") == "white t shirt"

    def test_cache_key_is_deterministic_and_case_insensitive(self) -> None:
        assert ProductSearchService.cache_key("Navy Chinos") == ProductSearchService.cache_key("navy chinos")
        assert ProductSearchService.cache_key("navy chinos") != ProductSearchService.cache_key("white trousers")
        assert ProductSearchService.cache_key("x").startswith("shopping:")

    async def test_search_without_key_is_an_error(self) -> None:
        svc = _service()
        svc._api_key = ""
        with pytest.raises(ProductSearchError, match="SERPAPI_API_KEY"):
            await svc.search("white trousers")

    def test_enabled_flag_off_overrides_key(self) -> None:
        svc = _service()
        svc._enabled = False
        assert svc.enabled is False

    def test_parse_results(self) -> None:
        data = {
            "shopping_results": [
                {"title": "Navy Chinos", "link": "https://a.in/1", "extracted_price": 1299, "source": "Amazon.in"},
                {"title": "Blue Pants", "link": "https://m.com/2", "price": "₹999", "source": "Myntra"},
            ]
        }
        results = _service(2)._parse_results(data)
        assert [r.price for r in results] == ["₹1299", "₹999"]

    def test_parse_results_skips_incomplete_and_lists_a_product_once(self) -> None:
        data = {
            "shopping_results": [
                {"title": "", "link": ""},
                {"title": "Good", "link": ""},
                {"title": "H&M Linen shirt", "link": "https://hm.com/1", "source": "H&M"},
                {"title": "H&M linen shirt", "link": "https://myntra.com/2", "source": "Myntra"},
            ]
        }
        assert [p.source for p in _service()._parse_results(data)] == ["H&M"]

    def test_budget_drops_listings_over_it_or_without_a_price(self) -> None:
        data = {
            "shopping_results": [
                {"title": "Cheap", "link": "https://a/1", "extracted_price": 900},
                {"title": "At budget", "link": "https://a/2", "extracted_price": 2000.0},
                {"title": "Over", "link": "https://a/3", "extracted_price": 2001},
                {"title": "No price", "link": "https://a/4", "price": "See site"},
            ]
        }
        assert [p.title for p in _service()._parse_results(data, max_price=2000)] == ["Cheap", "At budget"]
        assert len(_service()._parse_results(data)) == 4

    async def test_budget_is_not_sent_to_serpapi(self) -> None:
        # Live, SerpAPI's max_price with gl=in returned no results at all; the filter above does the job.
        response = MagicMock()
        response.json.return_value = {
            "shopping_results": [{"title": "Over", "link": "https://a/1", "extracted_price": 9}]
        }
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__.return_value = client
        with patch("backend.services.product_search.httpx.AsyncClient", return_value=client):
            assert await _service().search("navy chinos", max_price=5) == []
        assert "max_price" not in client.get.await_args.kwargs["params"]


class TestProductSearchTool:
    def _tool(
        self, cached: object = None, search: AsyncMock | None = None
    ) -> tuple[ProductSearchTool, MagicMock, AsyncMock]:
        svc = MagicMock(spec=ProductSearchService)
        svc.build_query.side_effect = ProductSearchService.build_query
        svc.cache_key.side_effect = ProductSearchService.cache_key
        svc.enabled = True
        svc._cache_ttl = 604800
        svc.search = search or AsyncMock(return_value=[_product(1)])
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=cached)
        return ProductSearchTool(svc, cache), svc, cache

    async def test_cache_hit_makes_no_search(self) -> None:
        tool, svc, _ = self._tool(cached=[_product(1).model_dump()])
        result = await tool.find_products("trousers", "white", "all")
        assert [p.title for p in result] == ["Test Product 1"]
        svc.search.assert_not_called()

    async def test_cache_miss_searches_once_and_stores_for_seven_days(self) -> None:
        tool, svc, cache = self._tool()
        await tool.find_products("trousers", "white", "menswear", max_price=1500)
        svc.search.assert_awaited_once_with("men white trousers", 1500)
        assert cache.set.await_args.args[2] == 604800

    async def test_the_budget_is_part_of_the_cache_key(self) -> None:
        tool, _, cache = self._tool()
        await tool.find_products("trousers", "white", "all")
        await tool.find_products("trousers", "white", "all", max_price=1500)
        keys = [c.args[0] for c in cache.get.await_args_list]
        assert keys[0] != keys[1]

    async def test_search_errors_reach_the_caller(self) -> None:
        tool, _, _ = self._tool(search=AsyncMock(side_effect=ProductSearchError("down")))
        with pytest.raises(ProductSearchError):
            await tool.find_products("trousers", "white", "all")


class TestGate:
    """Policy in code first, then Jev; nothing unchecked gets through."""

    TITLES = ("Black leather belt for men", "Black belt bag waist pouch", "Women's black skinny skirt belt")

    def _products(self) -> list[ProductLink]:
        return [
            ProductLink(title=t, price="₹999", link="https://e.com/p", thumbnail="", source="S") for t in self.TITLES
        ]

    async def test_keeps_and_ranks_by_verdict_after_the_buyer_policy(self) -> None:
        judge = MagicMock()
        judge.judge = AsyncMock(return_value=[ProductVerdict(0.95, 0.9, 0.9), ProductVerdict(0.1, 0.9, 0.9)])
        kept = await gate(judge, self._products(), Wanted("belt", "black", "menswear"))
        # The men's policy dropped the title naming a skirt before Jev saw it; Jev dropped the belt bag.
        assert judge.judge.await_args.args[1] == list(self.TITLES[:2])
        assert [p.title for p in kept] == [self.TITLES[0]]
        assert kept[0].match_score == round(0.95 * 0.9 * 0.9, 2) and "jev:" in kept[0].match_reason

    async def test_jev_failure_propagates(self) -> None:
        judge = MagicMock()
        judge.judge = AsyncMock(side_effect=JevUnavailableError("down"))
        with pytest.raises(JevUnavailableError):
            await gate(judge, self._products(), Wanted("belt", "black", "all"))
