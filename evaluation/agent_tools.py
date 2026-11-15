"""Does the chat agent pick the right tool with the right arguments? 28 scripted requests.

Each case is a user message (some after a short history with a real outfit from the engine)
plus the tool the agent should call and a check on its key arguments, e.g. "swap the shoes"
must call ``build_outfits`` with the shoes' id in ``exclude_item_ids``. Reported per model:

- **tool choice**: the expected tool was called (or no tool, for chit-chat), and the paid
  ``search_products`` was not called when it was not asked for;
- **arguments**: tool choice right *and* one call's key arguments pass the check;
- **first tool**: the first call was the expected tool (no detour through ``list_closet``);
- steps and tokens per turn, empty steps (no text, no call: the Phase 2 Gemini issue),
  replies sent back for naming an unseen id (``corrections``), turns stopped by a limit or by a
  second invented reply, and **invented ids** that still reached the user (must be 0).

The real loop (``agent.run_turn``) and real tools run on the demo closet held in memory with
fixed ids (so cached replies stay valid). ``search_products`` is a stub returning two fixed
listings, so the eval makes **no SerpAPI or Jev calls**; weather is a fixed 30 °C. Every model
reply is cached in ``evaluation/.cache/agent_tools/``, so a re-run costs nothing. First run:
about 24 turns × 2–3 calls × ~4k tokens per model, roughly $0.03 per model::

    poetry run python evaluation/agent_tools.py \
        --model openai/gpt-4o-mini google/gemini-2.5-flash-lite openai/gpt-4.1-nano
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import mean
from typing import Any
from unittest.mock import AsyncMock

from openai.types.chat import ChatCompletion

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import agent, toolkit  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.engine.outfits import Weather  # noqa: E402
from backend.engine.preferences import WearEvent  # noqa: E402
from backend.engine.requests import says_missing  # noqa: E402
from backend.models.records import WardrobeItem  # noqa: E402
from backend.schemas.taxonomy import Occasion  # noqa: E402
from backend.services import closet, wear  # noqa: E402
from backend.services.llm import LLMService  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "agent_tools"
REPORT = Path(__file__).resolve().parent / "agent_tools_eval.json"
TODAY = dt.date(2026, 11, 15)  # fixed, so the system prompt (and the cache key) never changes
USER = "agent-eval"


class CachedLLM(LLMService):
    """``complete_with_tools`` replies cached on disk by model and the full request."""

    calls = 0

    async def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, max_tokens: int
    ) -> ChatCompletion:
        request = json.dumps([self._settings.agent_model, messages, tools, max_tokens], sort_keys=True, default=str)
        path = CACHE_DIR / f"{hashlib.sha256(request.encode()).hexdigest()}.json"
        if path.exists():
            return ChatCompletion.model_validate_json(path.read_text())
        CachedLLM.calls += 1
        response = await super().complete_with_tools(messages, tools, max_tokens=max_tokens)
        # Empty replies are cached too: the agent's retry adds a nudge, so it is never this same request.
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(response.model_dump_json())
        return response


# ──────────────────────────────────────────────────────────────────────
#  The closet in memory
# ──────────────────────────────────────────────────────────────────────


def demo_rows() -> list[WardrobeItem]:
    return [
        WardrobeItem(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"synclook-demo/{n}"),
            user_id=USER,
            image=b"",
            image_hash=str(n),
            **tags.model_dump(mode="json"),
        )
        for n, (tags, _) in enumerate(closet.demo_items())
    ]


ROWS = demo_rows()
LOG: list[WearEvent] = []
LOGGED: list[dict[str, Any]] = []


async def _list_items(_db: object, _user_id: str) -> list[WardrobeItem]:
    return ROWS


async def _events(_db: object, _user_id: str) -> list[WearEvent]:
    return list(LOG)


async def _record(_db: object, _user_id: str, item_ids: list[uuid.UUID], action: str, occasion: Any, day: Any) -> Any:
    owned = {r.id for r in ROWS}
    if not set(item_ids) <= owned:
        raise wear.NotInClosetError("Some items are not in this closet")
    LOGGED.append({"item_ids": [str(i) for i in item_ids], "action": action, "date": str(day)})
    return type("Row", (), {"id": uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(LOGGED[-1]))})()


async def _stub_search(_ctx: toolkit.Ctx, args: Any) -> dict[str, Any]:
    price = args.max_price or 2500
    return {
        "query": f"{args.color.value} {args.garment_type.value}",
        "checked": 16,
        "products": [
            {"title": f"{args.color.value.title()} {args.garment_type.value} A", "price": f"₹{price - 300}",
             "source": "Shop A", "link": "https://example.com/a"},
            {"title": f"{args.color.value.title()} {args.garment_type.value} B", "price": f"₹{price - 50}",
             "source": "Shop B", "link": "https://example.com/b"},
        ],
        "note": None,
        "searches_left_today": 7,
    }  # fmt: skip


TOOLS = tuple(replace(t, run=_stub_search) if t.name == "search_products" else t for t in toolkit.TOOLS)


def ctx() -> toolkit.Ctx:
    weather = AsyncMock()
    weather.forecast = AsyncMock(return_value=Weather(temperature_c=30, rain=False))
    return toolkit.Ctx(
        db=AsyncMock(), user_id=USER, weather=weather, products=AsyncMock(), judge=AsyncMock(), cache=AsyncMock(),
        today=TODAY,
    )  # fmt: skip


# ──────────────────────────────────────────────────────────────────────
#  Cases
# ──────────────────────────────────────────────────────────────────────

ArgCheck = Callable[[dict[str, Any]], bool]
ASK = "ask"
"""Expected "tool" for a request the agent must answer with a question, writing nothing (a call refused is fine)."""


@dataclass
class Case:
    id: str
    message: str
    tool: str | None
    check: ArgCheck = lambda _a: True  # noqa: E731
    history: list[dict[str, str]] = field(default_factory=list)
    missing: str | None = None
    """The reply must tell the user the closet has no such item (``engine.requests.says_missing``)."""


def _occasion(*values: str) -> ArgCheck:
    return lambda a: a.get("occasion") in values


async def _shown(occasion: Occasion, question: str) -> tuple[list[dict[str, str]], list[list[dict[str, Any]]]]:
    """A real first answer: the engine's outfits, written the way the agent is told to write them."""
    out = await toolkit.build_outfits(ctx(), toolkit.BuildOutfitsArgs(occasion=occasion))
    looks = [o["items"] for o in out["outfits"]]
    text = " ".join(
        f"Outfit {n}: " + ", ".join(f"{i['label']} [{i['id']}]" for i in items) + "."
        for n, items in enumerate(looks, 1)
    )
    return [{"role": "user", "content": question}, {"role": "assistant", "content": text}], looks


async def cases() -> list[Case]:
    history, looks = await _shown(Occasion.SMART_CASUAL, "What should I wear for smart casual drinks?")
    history = [history[0], {"role": "assistant", "content": history[1]["content"].split(" Outfit 2:")[0]}]
    items = looks[0]
    ids = {i["id"] for i in items}
    three, interview = await _shown(Occasion.INTERVIEW, "What should I wear to my interview?")
    # The markdown list gpt-4o-mini wrote live, where "I wore this yesterday" logged outfit 1.
    live = [
        {"role": "user", "content": "What should I wear to a job interview?"},
        {"role": "assistant", "content": "Here are three outfit suggestions for your job interview:\n\n" + "\n\n".join(
            f"{n}. **Outfit {n}**:\n" + "\n".join(f"   - {i['label']} [{i['id']}]" for i in items)
            for n, items in enumerate(interview, 1)
        )},
    ]  # fmt: skip
    second = {i["id"] for i in interview[1]}
    shoes = next(i["id"] for i in items if i["type"] in {"sneakers", "loafers", "boots", "sandals", "shoes"})
    yesterday = str(TODAY - dt.timedelta(days=1))
    shop_history = [
        {"role": "user", "content": "Show me white loafers under 3000 rupees"},
        {"role": "assistant", "content": "Two checked listings: White loafers A (₹2700, Shop A) and White loafers B "
                                         "(₹2950, Shop B)."},
    ]  # fmt: skip
    return [
        Case("interview", "What should I wear to my job interview tomorrow?", "build_outfits", _occasion("interview")),
        Case("date", "Outfit for a dinner date tonight?", "build_outfits", _occasion("date_night")),
        Case("wedding", "My friend's wedding is on Saturday, what do I wear?", "build_outfits",
             _occasion("wedding_guest", "festive_ethnic")),
        Case("gym", "Heading to the gym in an hour, what do I put on?", "build_outfits", _occasion("gym_athleisure")),
        Case("brunch", "Something relaxed for Sunday brunch with family", "build_outfits",
             _occasion("everyday_casual", "smart_casual")),
        Case("office_city", "Office day in Mumbai today, what should I wear?", "build_outfits",
             lambda a: a.get("occasion") in {"business_casual", "business_formal"} and "mumbai" in
             str(a.get("place", "")).lower()),
        Case("cold_rain", "It's 5 degrees and pouring, I need something for the office", "build_outfits",
             lambda a: a.get("temperature_c") is not None and a["temperature_c"] < 12 and a.get("rain") is True),
        Case("swap_shoes", "Swap the shoes", "build_outfits", lambda a: shoes in a.get("exclude_item_ids", []),
             history),
        Case("warmer", "Something warmer please", "build_outfits",
             lambda a: a.get("temperature_c") is not None and a["temperature_c"] < 12, history),
        Case("wore_yesterday", "I wore this yesterday", "log_wear",
             lambda a: a.get("action") == "worn" and a.get("date") == yesterday and set(a.get("item_ids", [])) == ids,
             history),
        Case("save", "Love this one, save it for later", "log_wear",
             lambda a: a.get("action") == "saved" and set(a.get("item_ids", [])) == ids, history),
        Case("skip", "Not my style, skip this one", "log_wear", lambda a: a.get("action") == "skipped", history),
        Case("wore_which", "I wore this yesterday", ASK, history=three),  # 3 shown: it must ask which
        Case("wore_which_live", "I wore this yesterday", ASK, history=live),  # the reply style that failed live
        Case("wore_second", "I wore the second one yesterday", "log_wear",
             lambda a: a.get("date") == yesterday and set(a.get("item_ids", [])) == second, three),
        # Things the closet cannot have: say so, then offer the closest outfits (worded unlike head_to_head's).
        Case("no_swimsuit", "Beach day and I'll be swimming, which swimsuit should I wear?", "build_outfits",
             missing="swimwear"),
        Case("no_tuxedo", "Wedding reception tonight and I'd like to wear a tuxedo", "build_outfits",
             missing="tuxedo"),
        Case("no_ski", "Going skiing this weekend, what do I wear on the slopes?", "build_outfits",
             missing="ski gear"),
        Case("no_heels", "Party tonight: put together an outfit with heels and my olive dress", "build_outfits",
             missing="heels"),
        Case("gap", "What one thing should I buy next?", "find_gap_item"),
        Case("gap_menswear", "I only wear menswear. What's missing from my wardrobe?", "find_gap_item",
             lambda a: a.get("buyer") == "menswear"),
        Case("search", "Show me white loafers I can buy under 3000 rupees", "search_products",
             lambda a: a.get("garment_type") == "loafers" and a.get("color") == "white" and a.get("max_price") == 3000),
        Case("search_plain", "Find me beige sneakers to buy", "search_products",
             lambda a: a.get("garment_type") == "sneakers" and a.get("color") == "beige"),
        Case("cheaper", "Make it cheaper", "search_products",
             lambda a: a.get("garment_type") == "loafers" and (a.get("max_price") or 10**9) < 3000, shop_history),
        Case("count_shoes", "How many pairs of shoes do I own?", "list_closet"),
        Case("navy_blazer", "Do I have a navy blazer?", "list_closet"),
        Case("hello", "Hi! What can you do?", None),
        Case("off_topic", "What's the capital of France?", None),
    ]  # fmt: skip


# ──────────────────────────────────────────────────────────────────────
#  Run
# ──────────────────────────────────────────────────────────────────────

_BRACKETED = re.compile(r"\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]")


async def run_case(llm: LLMService, case: Case) -> dict[str, Any]:
    LOG.clear()
    LOGGED.clear()
    events = [e async for e in agent.run_turn(llm, ctx(), case.history, case.message, tools=TOOLS)]
    calls = []
    for e in events:
        if e["type"] == "tool_call":
            try:
                calls.append((e["name"], json.loads(e["arguments"] or "{}")))
            except json.JSONDecodeError:
                calls.append((e["name"], {}))
    names = [n for n, _ in calls]
    reply = next(e["text"] for e in events if e["type"] == "reply")
    if case.tool == ASK:  # nothing written to the wear log, and the reply asks
        tool_ok = not LOGGED and "?" in reply and "search_products" not in names
    elif case.tool is None:
        tool_ok = not names
    else:
        tool_ok = case.tool in names and ("search_products" not in names or case.tool == "search_products")
    args_ok = tool_ok and (case.tool in (None, ASK) or any(n == case.tool and case.check(a) for n, a in calls))
    args_ok = args_ok and (case.missing is None or says_missing(case.missing, reply))
    owned = {str(r.id) for r in ROWS}
    done = events[-1]
    return {
        "id": case.id,
        "expected": case.tool,
        "called": names,
        "tool_ok": tool_ok,
        "args_ok": args_ok,
        "first_ok": tool_ok if case.tool == ASK else (names[:1] == [case.tool]) if case.tool else not names,
        "steps": done["steps"],
        "tokens": done["tokens"],
        "empty_steps": done["empty_steps"],
        "corrections": done["corrections"],
        "stopped": done["stopped"],
        "invented_ids": [i for i in _BRACKETED.findall(reply) if i not in owned],
        "arguments": [a for _, a in calls],
        "reply": reply,
    }


async def run_model(model: str, all_cases: list[Case]) -> dict[str, Any]:
    settings = get_settings().model_copy(update={"agent_model": model})
    llm = CachedLLM(settings)
    before = CachedLLM.calls
    rows = [await run_case(llm, c) for c in all_cases]
    n = len(rows)
    summary = {
        "model": model,
        "cases": n,
        "tool_choice_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 3),
        "argument_accuracy": round(sum(r["args_ok"] for r in rows) / n, 3),
        "first_tool_accuracy": round(sum(r["first_ok"] for r in rows) / n, 3),
        "mean_steps": round(mean(r["steps"] for r in rows), 2),
        "max_steps": max(r["steps"] for r in rows),
        "mean_tokens": round(mean(r["tokens"] for r in rows)),
        "empty_steps": sum(r["empty_steps"] for r in rows),
        "corrections": sum(r["corrections"] for r in rows),
        "stopped_by_limit": sum(r["stopped"] is not None for r in rows),
        "invented_ids": sum(len(r["invented_ids"]) for r in rows),
        "new_model_calls": CachedLLM.calls - before,
    }
    return {"summary": summary, "cases": rows}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", nargs="+", default=[get_settings().agent_model])
    parser.add_argument("--only", nargs="*", help="Run only these case ids")
    args = parser.parse_args()

    closet.list_items = _list_items  # type: ignore[assignment]
    wear.events = _events  # type: ignore[assignment]
    wear.record = _record  # type: ignore[assignment]
    all_cases = await cases()
    if args.only:
        all_cases = [c for c in all_cases if c.id in args.only]
    print(f"{len(all_cases)} cases × {len(args.model)} model(s); uncached turns make ~2–3 calls of ~4k tokens each")

    results = [await run_model(m, all_cases) for m in args.model]
    for r in results:
        s = r["summary"]
        print(json.dumps(s))
        for row in r["cases"]:
            if not row["args_ok"]:
                print(f"  MISS {row['id']}: expected {row['expected']}, called {row['called']} {row['arguments']}")
    if not args.only:
        REPORT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
