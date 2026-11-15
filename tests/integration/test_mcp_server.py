"""The MCP server through the FastAPI app, with the SDK's own client over Streamable HTTP.

The demo closet and wear log are the fakes from ``test_closet_outfits_api``; ``search_products`` is
stubbed, so no SerpAPI or Jev call runs.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import httpx2
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from backend import mcp_server, toolkit
from backend.models.records import WearEvent
from backend.schemas.api import ProductLink, ShopSearchResponse
from backend.services import closet, wear
from tests.integration.test_closet_outfits_api import HEADERS, app  # noqa: F401  (the fixture)
from tests.unit.test_toolkit import DictCache


@pytest.fixture
def keys(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:  # noqa: F811
    """Key → closet, in memory; the database session is a mock."""
    issued: dict[str, str] = {}

    async def new_mcp_key(_db: object, user_id: str) -> str:
        issued[key := uuid.uuid4().hex] = user_id
        return key

    async def mcp_user(_db: object, key: str) -> str | None:
        return issued.get(key)

    @asynccontextmanager
    async def no_db() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    monkeypatch.setattr(closet, "new_mcp_key", new_mcp_key)
    monkeypatch.setattr(closet, "mcp_user", mcp_user)
    monkeypatch.setattr(mcp_server, "async_session_factory", no_db)
    monkeypatch.setattr(mcp_server, "get_cache", DictCache)
    return issued


async def _url(asgi: FastAPI) -> str:
    async with AsyncClient(transport=ASGITransport(app=asgi), base_url="http://test") as client:
        resp = await client.post("/api/v1/closet/mcp-key", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return str(resp.json()["url"])


@asynccontextmanager
async def _mcp(asgi: FastAPI, url: str) -> AsyncIterator[Client]:
    async with (
        asgi.state.mcp_sessions.run(),  # what the app's lifespan does in production
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=asgi)) as http,
        Client(streamable_http_client(url, http_client=http)) as client,
    ):
        yield client


def _json(result: Any) -> dict[str, Any]:
    out: dict[str, Any] = json.loads(result.content[0].text)
    return out


async def test_every_tool_works_over_mcp_on_the_demo_closet(
    app: FastAPI,  # noqa: F811
    keys: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def checked_products(*_args: Any) -> ShopSearchResponse:
        product = ProductLink(
            title="White Canvas Jacket", price="₹1,999", source="Shop", link="https://shop.test/1", thumbnail=""
        )
        return ShopSearchResponse(query="white jacket", checked=5, products=[product], note=None)

    recorded: list[tuple[Any, ...]] = []

    async def record(_db: object, *args: Any) -> WearEvent:
        recorded.append(args)
        return WearEvent(id=uuid.uuid4())

    monkeypatch.setattr(toolkit, "checked_products", checked_products)
    monkeypatch.setattr(wear, "record", record)
    url = await _url(app)
    assert url.startswith("http://test/api/v1/mcp/") and url.endswith("/")
    assert set(keys.values()) == {"visitor-1"}

    async with _mcp(app, url) as client:
        listed = (await client.list_tools()).tools
        assert [t.name for t in listed] == [t.name for t in toolkit.TOOLS]
        for t in listed:
            assert "Returns" in (t.description or "") and t.input_schema["type"] == "object"
        costly = {t.name for t in listed if "side effect or a cost" in (t.description or "")}
        assert costly == {"log_wear", "search_products"}
        assert [t.name for t in listed if not t.annotations or not t.annotations.read_only_hint] == ["log_wear"]

        closet_items = _json(await client.call_tool("list_closet", {}))
        assert closet_items["count"] == 27

        outfits = _json(await client.call_tool("build_outfits", {"occasion": "interview"}))
        assert outfits["outfits"]
        owned = {i["id"] for i in closet_items["items"]}
        assert all(i["id"] in owned for o in outfits["outfits"] for i in o["items"])

        gaps = _json(await client.call_tool("find_gap_item", {}))
        assert gaps["gaps"][0]["new_outfits"] > 0

        found = _json(await client.call_tool("search_products", {"garment_type": "jacket", "color": "white"}))
        assert found["products"][0]["title"] == "White Canvas Jacket"
        assert found["searches_left_today"] == 7

        first = [i["id"] for i in outfits["outfits"][0]["items"]]
        logged = await client.call_tool("log_wear", {"item_ids": first, "action": "worn"})
        assert not logged.is_error and _json(logged)["logged"]["items"] == len(first)
        assert recorded[0][0] == "visitor-1"  # the closet the key belongs to

        bad = await client.call_tool("build_outfits", {"occasion": "moon landing"})
        assert bad.is_error and "Bad arguments" in _json(bad)["error"]


async def test_a_wrong_key_is_refused_before_any_mcp_code(app: FastAPI, keys: dict[str, str]) -> None:  # noqa: F811
    await _url(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/mcp/not-a-key/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 404
    with pytest.raises(ExceptionGroup) as refused:
        async with _mcp(app, "http://test/api/v1/mcp/not-a-key/") as client:
            await client.list_tools()
    assert refused.group_contains(MCPError, match="Not Found")  # the HTTP 404, as the client reports it
