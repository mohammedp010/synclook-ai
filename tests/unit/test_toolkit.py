"""The tool layer over the demo closet: swaps go through the rules, the paid tool has a daily cap."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend import toolkit
from backend.agent import run_turn
from backend.core import budget
from backend.engine.outfits import Outfit, violations
from backend.engine.preferences import WearEvent
from backend.schemas.api import ShopSearchRequest, WearRequest
from backend.schemas.taxonomy import Occasion
from backend.services import closet, wear
from tests.integration.test_closet_outfits_api import demo_rows
from tests.unit.test_agent import FakeLLM, reply


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.data.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.data[key] = value


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> toolkit.Ctx:
    rows = demo_rows()

    async def list_items(_db: object, _user_id: str) -> list[Any]:
        return rows

    async def events(_db: object, _user_id: str) -> list[WearEvent]:
        return []

    monkeypatch.setattr(closet, "list_items", list_items)
    monkeypatch.setattr(wear, "events", events)
    return toolkit.Ctx(
        db=AsyncMock(), user_id="visitor-1", weather=AsyncMock(), products=AsyncMock(), judge=AsyncMock(),
        cache=DictCache(),  # type: ignore[arg-type]
        today=dt.date(2026, 11, 15),
    )  # fmt: skip


async def test_the_daily_cap_counts_and_then_refuses_without_counting() -> None:
    cache = DictCache()
    day = dt.date(2026, 11, 15)
    assert await budget.spend(cache, "x", 2, day) == 1  # type: ignore[arg-type]
    assert await budget.spend(cache, "x", 2, day) == 0  # type: ignore[arg-type]
    with pytest.raises(budget.BudgetExceededError):
        await budget.spend(cache, "x", 2, day)  # type: ignore[arg-type]
    assert cache.data == {"budget:x:2026-11-15": 2}
    assert await budget.spend(cache, "x", 2, day + dt.timedelta(days=1)) == 1  # type: ignore[arg-type]


async def test_a_swap_is_the_engine_again_without_that_item(ctx: toolkit.Ctx) -> None:
    args = toolkit.BuildOutfitsArgs(occasion=Occasion.SMART_CASUAL)
    first = await toolkit.build_outfits(ctx, args)
    shoes = next(
        i["id"] for i in first["outfits"][0]["items"] if i["type"] in {"sneakers", "loafers", "boots", "shoes"}
    )
    swapped = await toolkit.build_outfits(ctx, args.model_copy(update={"exclude_item_ids": [shoes]}))
    assert swapped["outfits"]
    by_id = {str(r.id): closet.engine_item(r) for r in await closet.list_items(ctx.db, "")}
    for o in swapped["outfits"]:
        ids = [i["id"] for i in o["items"]]
        assert shoes not in ids
        outfit = Outfit(tuple(by_id[i] for i in ids), o["score"], {}, ())
        assert violations(outfit, Occasion.SMART_CASUAL, None) == []
    json.dumps(swapped)  # what the model reads is plain JSON


async def test_warmer_means_a_cold_temperature_and_outerwear(ctx: toolkit.Ctx) -> None:
    out = await toolkit.build_outfits(ctx, toolkit.BuildOutfitsArgs(occasion=Occasion.SMART_CASUAL, temperature_c=6))
    assert out["weather"].startswith("6°C, cold")
    cats = {str(r.id): r.category for r in await closet.list_items(ctx.db, "")}
    assert all(any(cats[i["id"]] == "outerwear" for i in o["items"]) for o in out["outfits"])


async def test_excluding_everything_says_why(ctx: toolkit.Ctx) -> None:
    every = [str(r.id) for r in await closet.list_items(ctx.db, "")]
    out = await toolkit.build_outfits(
        ctx, toolkit.BuildOutfitsArgs(occasion=Occasion.INTERVIEW, exclude_item_ids=every)
    )
    assert out["outfits"] == [] and out["reason"] == "Every item in the closet was excluded."


async def test_list_closet_filters_by_category(ctx: toolkit.Ctx) -> None:
    out = await toolkit.list_closet(ctx, toolkit.ListClosetArgs(category="footwear"))  # type: ignore[arg-type]
    assert out["count"] > 0 and {i["category"] for i in out["items"]} == {"footwear"}


async def test_search_over_the_cap_never_reaches_the_shop(ctx: toolkit.Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(toolkit.get_settings(), "search_daily_cap", 0)
    request = ShopSearchRequest(garment_type="loafers", color="white")  # type: ignore[arg-type]
    with pytest.raises(budget.BudgetExceededError):
        await toolkit.search_products(ctx, request)
    ctx.products.find_products.assert_not_awaited()  # type: ignore[attr-defined]


async def test_log_wear_refuses_a_future_day_before_writing(ctx: toolkit.Ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    record = AsyncMock()
    monkeypatch.setattr(wear, "record", record)
    request = WearRequest(item_ids=[uuid.uuid4()], action="worn", date=dt.date(2026, 11, 16))
    with pytest.raises(toolkit.FutureDateError):
        await toolkit.log_wear(ctx, request)
    record.assert_not_awaited()


def test_every_tool_schema_is_plain_json_with_a_unique_name() -> None:
    names = [t.name for t in toolkit.TOOLS]
    assert names == ["list_closet", "build_outfits", "find_gap_item", "search_products", "log_wear"]
    for tool in toolkit.TOOLS:
        schema = json.loads(json.dumps(tool.schema()))
        assert schema["function"]["parameters"]["type"] == "object"


# ── "I wore this": with several outfits shown, the message must say which ──

A = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"]
B = ["33333333-3333-4333-8333-333333333333", "22222222-2222-4222-8222-222222222222"]
LABELS = {A[0]: "olive dress", A[1]: "navy watch", B[0]: "black blazer"}


def test_shown_outfits_reads_both_reply_styles() -> None:
    plain = f"Outfit 1: olive dress [{A[0]}], navy watch [{A[1]}]. Outfit 2: black blazer [{B[0]}], watch [{B[1]}]."
    markdown = f"Here are two:\n\n1. **Outfit 1**:\n   - olive dress [{A[0]}]\n   - navy watch [{A[1]}]\n\n" + (
        f"2. **Outfit 2**:\n   - black blazer [{B[0]}]\n   - navy watch [{B[1]}]\n"
    )
    assert toolkit.shown_outfits(plain) == toolkit.shown_outfits(markdown) == [A, B]
    assert toolkit.shown_outfits(f"Try the olive dress [{A[0]}] with the watch [{A[1]}].") == [A]
    assert toolkit.shown_outfits("Which occasion?") == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I wore this yesterday", None),
        ("I wore it last night", None),  # "last" is not a position
        ("I wore the second one yesterday", 1),
        ("wore outfit 1 today", 0),
        ("#2 please", 1),
        ("the one with the blazer", 1),  # only outfit 2 has a blazer
        ("the one with the watch", None),  # both have the watch
        ("the first or the second, not sure", None),
    ],
)
def test_pointed_outfit(message: str, expected: int | None) -> None:
    assert toolkit.pointed_outfit(message, [A, B], LABELS) == expected


async def test_an_ambiguous_wear_through_the_agent_logs_nothing_and_asks(
    ctx: toolkit.Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = AsyncMock()
    monkeypatch.setattr(wear, "record", record)
    rows = await closet.list_items(ctx.db, "")
    one, two = [str(r.id) for r in rows[:2]], [str(r.id) for r in rows[2:4]]
    history = [
        {"role": "user", "content": "What do I wear?"},
        {"role": "assistant", "content": "Outfit 1: " + ", ".join(f"x [{i}]" for i in one)
         + ". Outfit 2: " + ", ".join(f"y [{i}]" for i in two) + "."},
    ]  # fmt: skip
    call = json.dumps({"item_ids": one, "action": "worn", "date": "2026-11-14"})
    llm = FakeLLM(reply(calls=[("log_wear", call)]), reply("Which one did you wear, 1 or 2?"))
    events = [e async for e in run_turn(llm, ctx, history, "I wore this yesterday")]  # type: ignore[arg-type]
    result = next(e["result"] for e in events if e["type"] == "tool_result")
    assert result["needs_choice"] and [o["number"] for o in result["outfits"]] == [1, 2]
    record.assert_not_awaited()

    # Named by position, but the model passed the other outfit's ids: refused with the right ones.
    llm = FakeLLM(reply(calls=[("log_wear", call)]), reply("ok"))
    events = [e async for e in run_turn(llm, ctx, history, "I wore the second one")]  # type: ignore[arg-type]
    result = next(e["result"] for e in events if e["type"] == "tool_result")
    assert "outfit 2" in result["error"] and two[0] in result["error"]
    record.assert_not_awaited()


async def test_an_item_the_closet_lacks_comes_back_as_missing_and_is_said_first(ctx: toolkit.Ctx) -> None:
    ctx.message = "Pool party, I want a swimwear outfit"
    out = await toolkit.build_outfits(ctx, toolkit.BuildOutfitsArgs(occasion=Occasion.BEACH_RESORT))
    assert out["missing"] == ["swimwear"] and out["outfits"]  # the closest alternatives are still offered
    assert out["notes"][0].startswith("Not in the closet: swimwear")
    ctx.message = ""
    plain = await toolkit.build_outfits(ctx, toolkit.BuildOutfitsArgs(occasion=Occasion.BEACH_RESORT))
    assert plain["missing"] == []
    mcp = await toolkit.build_outfits(
        ctx, toolkit.BuildOutfitsArgs(occasion=Occasion.BEACH_RESORT, requested=["heels"])
    )
    assert mcp["missing"] == ["heels"]  # MCP has no message: the model's own list is checked too

    # The agent: a reply that skips the gap gets a fixed sentence in front; one that says it is left alone.
    call = json.dumps({"occasion": "beach_resort"})
    for text, prefixed in [
        ("Here are some swimwear outfits: ...", True),
        ("You have no swimwear. Closest: ...", False),
    ]:
        llm = FakeLLM(reply(calls=[("build_outfits", call)]), reply(text))
        events = [e async for e in run_turn(llm, ctx, [], "Swimwear outfit for the pool?")]  # type: ignore[arg-type]
        final = next(e["text"] for e in events if e["type"] == "reply")
        assert final.startswith("Your closet has no swimwear") is prefixed and final.endswith(text)
