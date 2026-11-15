"""Closet and outfit routes over ASGI, with the database, models and weather replaced by fakes."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app import create_app
from backend.core.dependencies import get_llm_service, get_perceiver, get_weather_service
from backend.db.session import get_db_session
from backend.engine.outfits import Weather
from backend.engine.preferences import WearEvent
from backend.models.records import WardrobeItem
from backend.schemas.intent import StyleIntent
from backend.schemas.taxonomy import Occasion
from backend.services import closet, wear
from backend.services.outfit_explainer import _Explanations

HEADERS = {"X-User-Id": "visitor-1"}


def demo_rows() -> list[WardrobeItem]:
    return [
        WardrobeItem(
            id=uuid.uuid4(), user_id="visitor-1", image=jpeg, image_hash=str(n), **tags.model_dump(mode="json")
        )
        for n, (tags, jpeg) in enumerate(closet.demo_items())
    ]


class FakeLLM:
    def __init__(self, occasion: Occasion | None = None) -> None:
        self.extract_intent = AsyncMock(return_value=StyleIntent(occasion_type=occasion))
        self.structured = AsyncMock(side_effect=self._words)

    async def _words(self, schema: type[Any], *, system_prompt: str, user_prompt: str) -> _Explanations:
        blocks = [b for b in user_prompt.split("\nOutfit ") if " pieces: " in b]
        return _Explanations(explanations=[b.split(" pieces: ")[1].split("\n")[0] + " work well." for b in blocks])


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    app = create_app()

    async def no_db() -> AsyncIterator[object]:
        yield AsyncMock()

    rows = demo_rows()

    async def list_items(_db: object, user_id: str) -> list[WardrobeItem]:
        return [r for r in rows if r.user_id == user_id]

    monkeypatch.setattr(closet, "list_items", list_items)
    app.state.wear_log = []

    async def events(_db: object, _user_id: str) -> list[WearEvent]:
        return list(app.state.wear_log)

    monkeypatch.setattr(wear, "events", events)
    app.dependency_overrides[get_db_session] = no_db
    app.dependency_overrides[get_llm_service] = lambda: FakeLLM(Occasion.DATE_NIGHT)
    weather = AsyncMock()
    weather.forecast = AsyncMock(return_value=Weather(temperature_c=8, rain=True))
    app.dependency_overrides[get_weather_service] = lambda: weather
    yield app


async def _post(app: FastAPI, path: str, **kwargs: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(f"/api/v1{path}", **kwargs)


async def test_an_occasion_value_gives_three_explained_outfits_without_parsing(app: FastAPI) -> None:
    llm = FakeLLM()
    app.dependency_overrides[get_llm_service] = lambda: llm
    resp = await _post(app, "/outfits", json={"occasion": "business formal"}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["occasion"] == "business_formal" and not body["occasion_from_text"]
    assert len(body["outfits"]) == 3 and body["reason"] is None and body["weather"] is None
    first = body["outfits"][0]
    assert first["explanation_source"] == "model" and first["evidence"]
    assert first["items"][0]["image_url"].endswith("/image")
    llm.extract_intent.assert_not_awaited()
    assert llm.structured.await_count == 1


async def test_free_text_is_parsed_and_weather_is_used(app: FastAPI) -> None:
    resp = await _post(app, "/outfits", json={"occasion": "dinner date tonight", "place": "Pune"}, headers=HEADERS)
    body = resp.json()
    assert body["occasion"] == "date_night" and body["occasion_from_text"]
    assert body["weather"] == {"temperature_c": 8.0, "band": "cold", "rain": True}
    assert all(any(i["category"] == "outerwear" for i in o["items"]) for o in body["outfits"])


async def test_text_with_no_occasion_is_a_422_listing_the_choices(app: FastAPI) -> None:
    app.dependency_overrides[get_llm_service] = lambda: FakeLLM(None)
    resp = await _post(app, "/outfits", json={"occasion": "hmm"}, headers=HEADERS)
    assert resp.status_code == 422 and "interview" in resp.json()["detail"]


async def test_an_empty_closet_says_so(app: FastAPI) -> None:
    resp = await _post(app, "/outfits", json={"occasion": "interview"}, headers={"X-User-Id": "someone-else"})
    body = resp.json()
    assert body["outfits"] == [] and "closet is empty" in body["reason"]


async def test_the_user_header_is_required(app: FastAPI) -> None:
    assert (await _post(app, "/outfits", json={"occasion": "interview"})).status_code == 422


async def test_upload_checks_run_before_any_paid_call(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    perceiver = AsyncMock()
    app.dependency_overrides[get_perceiver] = lambda: perceiver
    files = {"file": ("x.gif", b"GIF89a", "image/gif")}
    assert (await _post(app, "/closet/items", files=files, headers=HEADERS)).status_code == 415

    async def full(*_: object) -> None:
        raise closet.ClosetFullError("A closet holds at most 60 items")

    monkeypatch.setattr(closet, "check_can_add", full)
    resp = await _post(app, "/closet/items", files={"file": ("x.jpg", b"jpeg", "image/jpeg")}, headers=HEADERS)
    assert resp.status_code == 409 and "60" in resp.json()["detail"]
    perceiver.perceive.assert_not_awaited()


async def test_a_correction_with_an_unknown_type_is_rejected(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/closet/items/{uuid.uuid4()}", json={"garment_type": "spacesuit"}, headers=HEADERS
        )
    assert resp.status_code == 422


async def test_a_correction_updates_the_derived_tags() -> None:
    row = demo_rows()[0]
    session = AsyncMock()
    await closet.update(session, row, {"garment_type": "jeans", "color": "navy"})
    assert (row.category, row.color_family, row.garment_type) == ("bottomwear", "navy", "jeans")


# ── Wear log ─────────────────────────────────────────────────────────


async def _get(app: FastAPI, path: str) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(f"/api/v1{path}", headers=HEADERS)


def _db_owning(*ids: uuid.UUID) -> AsyncMock:
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=list(ids))
    session.add = lambda row: setattr(row, "id", uuid.uuid4())
    return session


async def test_wear_records_an_event_for_owned_items(app: FastAPI) -> None:
    mine = uuid.uuid4()
    session = _db_owning(mine)

    async def db() -> AsyncIterator[object]:
        yield session

    app.dependency_overrides[get_db_session] = db
    body = {"item_ids": [str(mine), str(mine)], "action": "worn", "occasion": "interview"}
    resp = await _post(app, "/wear", json=body, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert resp.json()["date"] == dt.date.today().isoformat() and resp.json()["occasion"] == "interview"
    session.commit.assert_awaited_once()


async def test_wear_rejects_items_outside_the_closet_and_future_days(app: FastAPI) -> None:
    session = _db_owning()  # owns none of them

    async def db() -> AsyncIterator[object]:
        yield session

    app.dependency_overrides[get_db_session] = db
    resp = await _post(app, "/wear", json={"item_ids": [str(uuid.uuid4())], "action": "saved"}, headers=HEADERS)
    assert resp.status_code == 404
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    body = {"item_ids": [str(uuid.uuid4())], "action": "worn", "date": tomorrow}
    assert (await _post(app, "/wear", json=body, headers=HEADERS)).status_code == 422
    bad = {"item_ids": [str(uuid.uuid4())], "action": "loved"}
    assert (await _post(app, "/wear", json=bad, headers=HEADERS)).status_code == 422
    session.commit.assert_not_awaited()


async def test_stats_count_wears_per_item_and_list_the_never_worn(app: FastAPI) -> None:
    items = (await _get(app, "/closet/items")).json()
    a, b = items[0]["id"], items[1]["id"]
    day = dt.date(2026, 11, 10)
    app.state.wear_log = [WearEvent((a, b), "worn", day), WearEvent((a,), "worn", day + dt.timedelta(days=1))]
    body = (await _get(app, "/closet/stats")).json()
    assert body["items"][0] == {
        "id": a,
        "short_label": items[0]["short_label"],
        "times_worn": 2,
        "last_worn": "2026-11-11",
    }
    assert body["items"][1]["times_worn"] == 1
    assert len(body["never_worn"]) == len(items) - 2 and a not in body["never_worn"]


async def test_outfits_learn_from_the_wear_log(app: FastAPI) -> None:
    first = (await _post(app, "/outfits", json={"occasion": "everyday casual"}, headers=HEADERS)).json()["outfits"][0]
    ids = tuple(i["id"] for i in first["items"])
    app.state.wear_log = [WearEvent(ids, "worn", dt.date.today())]
    again = (await _post(app, "/outfits", json={"occasion": "everyday casual"}, headers=HEADERS)).json()["outfits"]
    assert all(o["score_parts"]["recently_worn"] <= 0 for o in again)
    assert tuple(i["id"] for i in again[0]["items"]) != ids  # worn today → rotated down
    assert any(o["score_parts"]["preference"] > 0 for o in again)
