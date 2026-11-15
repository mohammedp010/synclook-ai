"""The tool layer: five typed functions over the closet, the outfit engine, the gap finder,
the product gate and the wear log.

The chat agent (``agent.py``) and the MCP server (``mcp_server.py``) both run ``TOOLS`` through
``run_tool``. Each tool returns compact JSON a model can read. Nothing here is a second copy:
the routes call ``closet_outfits``, ``checked_products`` and ``record_wear`` too, and every
outfit still comes from ``engine.outfits``, so a model can pick a tool but never an item.

Only ``search_products`` costs money (one SerpAPI search, cached 7 days, plus one Jev call);
it counts against ``settings.search_daily_cap`` first.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import budget
from backend.core.config import get_settings
from backend.core.exceptions import ProductSearchError, SynclookError
from backend.core.logging import get_logger
from backend.engine.gaps import find_gaps
from backend.engine.outfits import ClosetItem, OutfitResult, Weather
from backend.engine.outfits import build_outfits as engine_outfits
from backend.engine.preferences import item_preferences, recently_worn
from backend.engine.requests import missing_requested
from backend.schemas.api import GapsRequest, ShopSearchRequest, ShopSearchResponse, WearOut, WearRequest
from backend.schemas.taxonomy import GarmentCategory, Occasion
from backend.services import closet, wear
from backend.services.cache import KvCache
from backend.services.jev import JevError
from backend.services.product_judge import ProductJudge, Wanted, gate
from backend.services.weather import WeatherService
from backend.tools.product_search import ProductSearchTool

logger = get_logger(__name__)

EMPTY_CLOSET = "Your closet is empty: add items, or POST /closet/demo to try the demo closet."


class FutureDateError(ValueError):
    pass


@dataclass
class Ctx:
    """What one request's tools need: whose closet, a database session and the services."""

    db: AsyncSession
    user_id: str
    weather: WeatherService
    products: ProductSearchTool
    judge: ProductJudge
    cache: KvCache
    today: dt.date = field(default_factory=dt.date.today)
    message: str = ""
    """The user's message this turn (set by the agent); ``log_wear`` reads which outfit it points at."""
    shown: str = ""
    """The latest assistant message that named items; ``log_wear`` reads the outfits it offered."""


# ──────────────────────────────────────────────────────────────────────
#  Shared with the routes
# ──────────────────────────────────────────────────────────────────────


async def closet_outfits(
    db: AsyncSession,
    user_id: str,
    occasion: Occasion,
    weather: Weather | None,
    day: dt.date,
    exclude: Collection[str] = (),
    requested: Collection[str] = (),
) -> OutfitResult:
    """The engine's top 3 from this closet, ranked with the wear log. *exclude* drops items (a swap).
    *requested* is the user's own words; anything it names that the closet lacks comes back in ``missing``."""
    rows = await closet.list_items(db, user_id)
    if not rows:
        return OutfitResult([], reason=EMPTY_CLOSET)
    everything = [closet.engine_item(r) for r in rows]
    missing = missing_requested(requested, (i.garment_type for i in everything))
    log = await wear.events(db, user_id)
    prefs = item_preferences(log, everything)  # on the whole closet, so an excluded item still informs its pair
    items = [i for i in everything if i.id not in exclude]
    if not items:
        return OutfitResult([], reason="Every item in the closet was excluded.", missing=missing)
    result = engine_outfits(items, occasion, weather, preferences=prefs, recently_worn=recently_worn(log, day))
    return replace(result, missing=missing)


async def checked_products(
    tool: ProductSearchTool, judge: ProductJudge, request: ShopSearchRequest
) -> ShopSearchResponse:
    """Products for one item: one SerpAPI search (cached 7 days), one Jev call. Only checked products are shown."""
    item = request.garment_type.value
    query = tool.query(item, request.color.value, request.buyer)
    try:
        pool = await tool.find_products(item, request.color.value, request.buyer, request.max_price)
    except ProductSearchError as exc:
        logger.warning("shop_search_failed", error=str(exc))
        return ShopSearchResponse(query=query, checked=0, products=[], note="Product search is unavailable right now.")
    if not pool:
        budget_text = f" under ₹{request.max_price}" if request.max_price else ""
        return ShopSearchResponse(query=query, checked=0, products=[], note=f"No listings found{budget_text}.")
    wanted = Wanted(item=item.replace("_", " "), colour=request.color.value, shopping_intent=request.buyer)
    try:
        kept = await gate(judge, pool, wanted)
    except JevError as exc:
        # No unmeasured fallback: an unchecked product is worse than none.
        logger.warning("product_judge_failed", error=str(exc))
        return ShopSearchResponse(
            query=query,
            checked=0,
            products=[],
            note="The product checker is unavailable, so no products are shown (unchecked listings never are).",
        )
    note = None if kept else f"None of the {len(pool)} listings passed the check for {wanted.colour} {wanted.item}."
    return ShopSearchResponse(query=query, checked=len(pool), products=kept, note=note)


async def record_wear(db: AsyncSession, user_id: str, request: WearRequest, today: dt.date) -> WearOut:
    """Save one wear event and commit. Raises ``FutureDateError`` or ``wear.NotInClosetError``."""
    day = request.date or today
    if day > today:
        raise FutureDateError("A wear event cannot be in the future")
    row = await wear.record(
        db, user_id, request.item_ids, request.action, request.occasion and request.occasion.value, day
    )
    await db.commit()
    return WearOut(**request.model_dump(exclude={"date"}), id=row.id, date=day)


# ──────────────────────────────────────────────────────────────────────
#  The five tools
# ──────────────────────────────────────────────────────────────────────


def _item(i: ClosetItem) -> dict[str, Any]:
    return {
        "id": i.id,
        "label": i.short_label,
        "type": i.garment_type,
        "category": i.category.value,
        "color": i.color_family,
        "formality": i.formality.name.lower(),
        "warmth": i.warmth.value,
    }


class ListClosetArgs(BaseModel):
    category: GarmentCategory | None = Field(default=None, description="Only this category; every item when omitted")


async def list_closet(ctx: Ctx, args: ListClosetArgs) -> dict[str, Any]:
    items = [closet.engine_item(r) for r in await closet.list_items(ctx.db, ctx.user_id)]
    if args.category:
        items = [i for i in items if i.category == args.category]
    out: dict[str, Any] = {"count": len(items), "items": [_item(i) for i in items]}
    if not items:
        out["reason"] = EMPTY_CLOSET if args.category is None else f"No {args.category.value} items in the closet."
    return out


class BuildOutfitsArgs(BaseModel):
    occasion: Occasion
    exclude_item_ids: list[str] = Field(
        default_factory=list,
        max_length=60,
        description="Ids of closet items to leave out, e.g. the shoes the user wants swapped",
    )
    place: str | None = Field(default=None, max_length=120, description="City, to use its real forecast")
    temperature_c: float | None = Field(
        default=None,
        ge=-30,
        le=50,
        description="Use when the user states the weather or asks for something warmer or cooler. "
        "Below 12 is cold (adds outerwear), 12-25 mild (no change), 26+ hot: so 'warmer' means about 8 "
        "and 'cooler' about 28. Overrides place",
    )
    rain: bool = Field(default=False, description="Rain expected; only used together with temperature_c")
    requested: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Garments or accessories the user asked to wear, in their words (e.g. 'heels', 'swimsuit'); "
        "the result says which ones the closet does not have",
    )
    date: dt.date | None = Field(default=None, description="Day to dress for; today when omitted")


async def build_outfits(ctx: Ctx, args: BuildOutfitsArgs) -> dict[str, Any]:
    day = args.date or ctx.today
    weather, notes = None, []
    if args.temperature_c is not None:
        weather = Weather(temperature_c=args.temperature_c, rain=args.rain)
    elif args.place:
        weather = await ctx.weather.forecast(place=args.place, day=day)
        if weather is None:
            notes.append("Weather was unavailable; these outfits ignore it")
    words = [ctx.message, *args.requested]  # the message too: the model may not fill ``requested``
    result = await closet_outfits(
        ctx.db, ctx.user_id, args.occasion, weather, day, set(args.exclude_item_ids), requested=words
    )
    if result.missing:
        notes.insert(0, f"Not in the closet: {', '.join(result.missing)}. Say so first; these outfits are only the "
                     "closest alternatives.")  # fmt: skip
    return {
        "occasion": args.occasion.value,
        "weather": weather.describe() if weather else None,
        "outfits": [
            {
                "items": [{"id": i.id, "label": i.short_label, "type": i.garment_type} for i in o.items],
                "score": o.score,
                "evidence": list(o.evidence),
            }
            for o in result.outfits
        ],
        "reason": result.reason,
        "missing": result.missing,
        "notes": notes + result.notes,
    }


async def find_gap_item(ctx: Ctx, args: GapsRequest) -> dict[str, Any]:
    items = [closet.engine_item(r) for r in await closet.list_items(ctx.db, ctx.user_id)]
    if not items:
        return {"gaps": [], "reason": EMPTY_CLOSET}
    return {
        "gaps": [
            {
                "garment_type": g.garment_type,
                "color": g.color_family,
                "label": g.label,
                "new_outfits": g.new_outfits,
                "occasions_unlocked": [o.value for o in g.unlocked],
                "example_occasion": g.example_occasion.value,
                "example": [i.short_label for i in g.example.items],
            }
            for g in find_gaps(items, args.buyer)
        ]
    }


async def search_products(ctx: Ctx, args: ShopSearchRequest) -> dict[str, Any]:
    left = await budget.spend(ctx.cache, "product_searches", get_settings().search_daily_cap)
    found = await checked_products(ctx.products, ctx.judge, args)
    return {
        "query": found.query,
        "checked": found.checked,
        "products": [{"title": p.title, "price": p.price, "source": p.source, "link": p.link} for p in found.products],
        "note": found.note,
        "searches_left_today": left,
    }


_ID = re.compile(r"\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]")
_OUTFIT_MARK = re.compile(r"\b(?:outfit|look|option)\s*#?\d+", re.IGNORECASE)
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
_NUMBERED = re.compile(r"\b(?:outfit|look|option|number)\s*#?(\d)\b|#(\d)\b")
_WORD = re.compile(r"[a-z]+")


def shown_outfits(text: str) -> list[list[str]]:
    """The item ids of each outfit in a reply that labels them "Outfit 1", "Outfit 2", …

    A reply without such labels counts as one outfit. Lines before the first label (no ids) are dropped.
    """
    parts = _OUTFIT_MARK.split(text)
    groups = [list(dict.fromkeys(_ID.findall(p))) for p in parts]
    return [g for g in groups if g]


def pointed_outfit(message: str, outfits: list[list[str]], labels: dict[str, str]) -> int | None:
    """Which of *outfits* the user's *message* singles out (0-based), or None when it does not say.

    By position ("the second one", "outfit 2", "#2") or by a word only one outfit's labels contain
    ("the one with the blazer"). "This" or "it" with several outfits shown is None: ask.
    """
    text = message.lower()
    hits = {i for w, i in _ORDINALS.items() if re.search(rf"\b{w}\b", text)}
    hits |= {int(a or b) - 1 for a, b in _NUMBERED.findall(text)}
    hits = {i for i in hits if 0 <= i < len(outfits)}
    if hits:
        return hits.pop() if len(hits) == 1 else None
    said = set(_WORD.findall(text))
    words = [{w for i in o for w in _WORD.findall(labels.get(i, "").lower())} for o in outfits]
    only = []
    for n, mine in enumerate(words):
        others = set().union(*(w for m, w in enumerate(words) if m != n))
        if said & (mine - others):
            only.append(n)
    return only[0] if len(only) == 1 else None


async def log_wear(ctx: Ctx, args: WearRequest) -> dict[str, Any]:
    # Live, "I wore this yesterday" after 3 outfits logged outfit 1, and the prompt rule "ask if unclear" did not stop
    # it. So the code decides: with several outfits on screen, the message itself must say which one.
    outfits = shown_outfits(ctx.shown)
    ids = {str(i) for i in args.item_ids}
    if len(outfits) > 1 and ids <= {i for o in outfits for i in o}:
        labels = {str(r.id): r.short_label for r in await closet.list_items(ctx.db, ctx.user_id)}
        pick = pointed_outfit(ctx.message, outfits, labels)
        if pick is None:
            return {
                "needs_choice": True,
                "logged": None,
                "question": f"Nothing logged yet. Ask the user which outfit they mean (1 to {len(outfits)}).",
                "outfits": [
                    {"number": n, "items": [f"{labels.get(i, 'item')} [{i}]" for i in o]}
                    for n, o in enumerate(outfits, 1)
                ],
            }
        if not ids <= set(outfits[pick]):
            return {"error": f"The user means outfit {pick + 1}; log only its item ids: {', '.join(outfits[pick])}"}
    out = await record_wear(ctx.db, ctx.user_id, args, ctx.today)
    return {"logged": {"id": str(out.id), "items": len(out.item_ids), "action": out.action, "date": str(out.date)}}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[Ctx, Any], Awaitable[dict[str, Any]]]

    def schema(self) -> dict[str, Any]:
        """The OpenAI/OpenRouter ``tools`` entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args.model_json_schema(),
            },
        }


TOOLS = (
    Tool(
        "list_closet",
        "List the user's closet items (id, label, type, category, colour, formality, warmth). "
        "Use it to find an item's id or to answer what the user owns. Free.",
        ListClosetArgs,
        list_closet,
    ),
    Tool(
        "build_outfits",
        "Build up to 3 valid outfits from the user's own closet for an occasion, ranked by the style rules "
        "and what the user usually wears. The only way to make or change an outfit: to swap a piece, call it "
        "again with that piece's id in exclude_item_ids; for warmer or cooler, set temperature_c. Free.",
        BuildOutfitsArgs,
        build_outfits,
    ),
    Tool(
        "find_gap_item",
        "Find the one item to buy that adds the most new outfits to this closet (top 3, with counts). "
        "Use for 'what should I buy'. Free; it does not search shops.",
        GapsRequest,
        find_gap_item,
    ),
    Tool(
        "search_products",
        "Search shops for one item (garment type + colour, optional budget max_price in ₹) and return only "
        "listings that passed the product check. COSTS MONEY and has a daily limit: call it only when the user "
        "wants to see products to buy. For 'cheaper', call it again with a lower max_price.",
        ShopSearchRequest,
        search_products,
    ),
    Tool(
        "log_wear",
        "Record that the user wore, saved or skipped ONE outfit (its closet item ids) on a day, default today. "
        "Changes the wear log, which changes future outfit ranking. Call it once per outfit the user names; "
        "if several outfits were shown and the user did not say which, ask instead of calling it.",
        WearRequest,
        log_wear,
    ),
)

# Errors a tool may raise on bad input or a spent budget; anything else is logged as a bug.
_EXPECTED = (SynclookError, wear.NotInClosetError, ValueError)  # ValueError covers FutureDateError


async def run_tool(tools: dict[str, Tool], ctx: Ctx, name: str, raw_args: str) -> dict[str, Any]:
    """Validate the model's arguments and run one tool. Used by the chat agent and the MCP server.

    A bad name, bad arguments or a failing tool become an ``{"error": ...}`` result the model can read, never a crash.
    """
    tool = tools.get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}. Tools: {', '.join(tools)}"}
    try:
        args = tool.args.model_validate_json(raw_args or "{}")
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in exc.errors())
        return {"error": f"Bad arguments for {name}: {problems}"}
    try:
        return await tool.run(ctx, args)
    except _EXPECTED as exc:
        await ctx.db.rollback()
        return {"error": str(exc)}
    except Exception as exc:  # a bug in a tool must not crash the caller; the model is told it failed
        logger.exception("tool_crashed", tool=name)
        await ctx.db.rollback()
        return {"error": f"{name} failed: {type(exc).__name__}"}
