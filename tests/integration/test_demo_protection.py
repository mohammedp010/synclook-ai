"""The public demo protects itself: daily caps on paid calls (429, free parts keep working), per-visitor
rate limits, a body-size limit, docs on, and host database URLs that asyncpg can use."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.core.config import Settings, get_settings
from backend.core.dependencies import get_llm_service, get_perceiver, get_product_judge, get_product_search_tool
from backend.services import closet
from tests.integration.test_closet_outfits_api import HEADERS, FakeLLM, app  # noqa: F401  (the fixture)


async def _post(asgi: FastAPI, path: str, **kwargs: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=asgi), base_url="http://test") as client:
        return await client.post(f"/api/v1{path}", **kwargs)


@pytest.fixture
def spent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every daily cap at 0, as on a day the demo budget is used up."""
    for cap in ("search_daily_cap", "upload_daily_cap", "chat_daily_cap", "explanation_daily_cap"):
        monkeypatch.setattr(get_settings(), cap, 0)


def _is_budget_429(resp: Any) -> bool:
    return (
        resp.status_code == 429
        and resp.json()["detail"].startswith("Demo budget used for today")
        and 0 < int(resp.headers["retry-after"]) <= 86400
    )


async def test_over_the_caps_paid_routes_say_so_and_call_nothing(
    app: FastAPI,  # noqa: F811
    spent: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(closet, "check_can_add", AsyncMock())  # room in the closet, a new photo
    perceiver, tool, judge = AsyncMock(), AsyncMock(), AsyncMock()
    app.dependency_overrides[get_perceiver] = lambda: perceiver
    app.dependency_overrides[get_product_search_tool] = lambda: tool
    app.dependency_overrides[get_product_judge] = lambda: judge

    upload = await _post(app, "/closet/items", files={"file": ("x.jpg", b"jpeg", "image/jpeg")}, headers=HEADERS)
    search = await _post(app, "/shop/search", json={"garment_type": "loafers", "color": "white"}, headers=HEADERS)
    chat = await _post(app, "/chat", json={"message": "what do I wear?"}, headers=HEADERS)

    assert _is_budget_429(upload) and _is_budget_429(search) and _is_budget_429(chat)
    assert "product searches" in search.json()["detail"] and "photo uploads" in upload.json()["detail"]
    perceiver.perceive.assert_not_awaited()
    tool.find_products.assert_not_called()


async def test_over_the_caps_outfits_and_gaps_still_work(app: FastAPI, spent: None) -> None:  # noqa: F811
    llm = FakeLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    resp = await _post(app, "/outfits", json={"occasion": "interview"}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["outfits"]) == 3 and {o["explanation_source"] for o in body["outfits"]} == {"template"}
    assert any("Demo budget" in n for n in body["notes"])
    llm.structured.assert_not_awaited()

    free_text = await _post(app, "/outfits", json={"occasion": "a dinner date"}, headers=HEADERS)
    assert free_text.status_code == 429 and "interview" in free_text.json()["detail"]
    llm.extract_intent.assert_not_awaited()

    assert (await _post(app, "/shop/gaps", headers=HEADERS)).status_code == 200


async def test_the_cap_is_shared_and_counts_each_search_once(
    app: FastAPI,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    memory_cache_and_fresh_limits: dict[str, Any],
) -> None:
    monkeypatch.setattr(get_settings(), "search_daily_cap", 1)
    tool = AsyncMock()
    tool.query = lambda *_: "men white loafers"
    tool.find_products = AsyncMock(return_value=[])
    app.dependency_overrides[get_product_search_tool] = lambda: tool
    body = {"garment_type": "loafers", "color": "white"}
    assert (await _post(app, "/shop/search", json=body, headers=HEADERS)).status_code == 200
    assert _is_budget_429(await _post(app, "/shop/search", json=body, headers={"X-User-Id": "someone-else"}))
    assert list(memory_cache_and_fresh_limits.values()) == [1]


async def test_one_visitor_gets_three_searches_an_hour(app: FastAPI) -> None:  # noqa: F811
    tool = AsyncMock()
    tool.query = lambda *_: "q"
    tool.find_products = AsyncMock(return_value=[])
    app.dependency_overrides[get_product_search_tool] = lambda: tool
    codes = [
        (await _post(app, "/shop/search", json={"garment_type": "loafers", "color": "white"}, headers=HEADERS))
        .status_code
        for _ in range(4)
    ]  # fmt: skip
    assert codes == [200, 200, 200, 429]


async def test_the_mcp_endpoint_is_rate_limited_before_the_key_check(
    app: FastAPI,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit", "2/minute")
    codes = [(await _post(app, "/mcp/not-a-key/", json={})).status_code for _ in range(3)]
    assert codes[2] == 429


async def test_a_huge_body_is_refused_before_it_is_read(app: FastAPI) -> None:  # noqa: F811
    headers = {**HEADERS, "content-length": str(get_settings().max_upload_size_bytes * 2)}
    resp = await _post(app, "/closet/items", content=b"x", headers=headers)
    assert resp.status_code == 413


async def test_docs_are_on_and_the_root_points_at_them(app: FastAPI) -> None:  # noqa: F811
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 200
        root = await client.get("/")
    assert root.status_code == 307 and root.headers["location"] == "/docs"


@pytest.mark.parametrize(
    ("given", "used"),
    [
        (
            "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require",
        ),
        ("postgres://u:p@h/db?channel_binding=require&sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        ("postgresql+asyncpg://u:p@localhost:5432/db", "postgresql+asyncpg://u:p@localhost:5432/db"),
    ],
)
def test_a_host_database_url_is_made_asyncpg_ready(given: str, used: str) -> None:
    assert Settings(database_url=given).database_url == used
