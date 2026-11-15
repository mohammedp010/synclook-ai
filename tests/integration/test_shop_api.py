"""Shop routes over ASGI: the database, SerpAPI tool and Jev judge are fakes; nothing paid is called."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app import create_app
from backend.core.dependencies import get_product_judge, get_product_search_tool
from backend.core.exceptions import ProductSearchError
from backend.db.session import get_db_session
from backend.models.records import WardrobeItem
from backend.schemas.api import ProductLink
from backend.services import closet
from backend.services.jev import JevUnavailableError
from backend.services.product_judge import ProductVerdict
from backend.services.product_search import ProductSearchService
from tests.integration.test_closet_outfits_api import HEADERS, demo_rows

TITLES = ["Men white sneakers", "White sneaker laces", "Men white canvas sneakers"]


def _pool() -> list[ProductLink]:
    return [
        ProductLink(title=t, price="₹999", link=f"https://shop/{n}", thumbnail="", source="S")
        for n, t in enumerate(TITLES)
    ]


@pytest.fixture
def fakes() -> dict[str, Any]:
    tool = MagicMock()
    tool.query.side_effect = lambda item, colour, buyer: ProductSearchService.build_query(item, colour, "", buyer)
    tool.find_products = AsyncMock(return_value=_pool())
    judge = MagicMock()
    judge.judge = AsyncMock(
        return_value=[ProductVerdict(0.9, 0.9, 0.9), ProductVerdict(0.1, 0.9, 0.9), ProductVerdict(0.8, 0.9, 0.9)]
    )
    return {"tool": tool, "judge": judge}


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, fakes: dict[str, Any]) -> Iterator[FastAPI]:
    app = create_app()

    async def no_db() -> AsyncIterator[object]:
        yield AsyncMock()

    rows = demo_rows()

    async def list_items(_db: object, user_id: str) -> list[WardrobeItem]:
        return [r for r in rows if r.user_id == user_id]

    monkeypatch.setattr(closet, "list_items", list_items)
    app.dependency_overrides[get_db_session] = no_db
    app.dependency_overrides[get_product_search_tool] = lambda: fakes["tool"]
    app.dependency_overrides[get_product_judge] = lambda: fakes["judge"]
    yield app


async def _post(app: FastAPI, path: str, **kwargs: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(f"/api/v1{path}", **kwargs)


async def test_gaps_on_the_demo_closet_suggest_three_items_with_an_example(app: FastAPI, fakes: dict[str, Any]) -> None:
    resp = await _post(app, "/shop/gaps", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["gaps"]) == 3 and body["reason"] is None and 0 < body["candidates_checked"] <= 40
    for gap in body["gaps"]:
        assert gap["new_outfits"] > 0 and gap["example_evidence"]
        to_buy = [p for p in gap["example"] if p["id"] is None]
        assert len(to_buy) == 1 and to_buy[0]["image_url"] is None
    fakes["tool"].find_products.assert_not_called()
    fakes["judge"].judge.assert_not_called()


async def test_gaps_for_an_empty_closet_say_how_to_start(app: FastAPI) -> None:
    resp = await _post(app, "/shop/gaps", headers={"X-User-Id": "nobody"}, json={"buyer": "menswear"})
    assert resp.status_code == 200 and resp.json()["gaps"] == []
    assert "POST /closet/demo" in resp.json()["reason"]


async def test_search_shows_only_gated_products_best_first(app: FastAPI, fakes: dict[str, Any]) -> None:
    body = {"garment_type": "sneakers", "color": "white", "buyer": "menswear", "max_price": 3000}
    resp = await _post(app, "/shop/search", headers=HEADERS, json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["query"] == "men white sneakers" and out["checked"] == 3 and out["note"] is None
    assert [p["title"] for p in out["products"]] == [TITLES[0], TITLES[2]]
    fakes["tool"].find_products.assert_awaited_once_with("sneakers", "white", "menswear", 3000)
    fakes["judge"].judge.assert_awaited_once()


async def test_search_says_so_when_jev_is_down(app: FastAPI, fakes: dict[str, Any]) -> None:
    fakes["judge"].judge = AsyncMock(side_effect=JevUnavailableError("down"))
    resp = await _post(app, "/shop/search", headers=HEADERS, json={"garment_type": "chinos", "color": "navy"})
    out = resp.json()
    assert resp.status_code == 200 and out["products"] == [] and "checker is unavailable" in out["note"]


async def test_search_says_so_when_serpapi_fails_or_finds_nothing(app: FastAPI, fakes: dict[str, Any]) -> None:
    fakes["tool"].find_products = AsyncMock(side_effect=ProductSearchError("down"))
    out = (await _post(app, "/shop/search", headers=HEADERS, json={"garment_type": "chinos", "color": "navy"})).json()
    assert out["products"] == [] and "unavailable" in out["note"]
    fakes["tool"].find_products = AsyncMock(return_value=[])
    body = {"garment_type": "chinos", "color": "navy", "max_price": 500}
    out = (await _post(app, "/shop/search", headers=HEADERS, json=body)).json()
    assert out["products"] == [] and out["note"] == "No listings found under ₹500."
    fakes["judge"].judge.assert_not_called()


async def test_search_rejects_unknown_items_and_needs_the_closet_header(app: FastAPI) -> None:
    assert (
        await _post(app, "/shop/search", headers=HEADERS, json={"garment_type": "spaceship", "color": "navy"})
    ).status_code == 422
    assert (await _post(app, "/shop/search", json={"garment_type": "chinos", "color": "navy"})).status_code == 422
