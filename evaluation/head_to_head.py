"""Synclook against a plain chatbot: the same 30 questions over the same demo closet.

Interviewers ask "why not just use ChatGPT?". This puts numbers on it, scored by code:

- **Arm 1, Synclook**: the real chat agent (``agent.run_turn`` on ``agent_model``) with the real
  tools on the demo closet held in memory, as ``agent_tools.py`` does. ``search_products`` is the
  real one (SerpAPI + the Jev gate); its whole result is cached on disk, so a re-run spends nothing.
- **Arm 2, plain chatbot**: ``ARM2_MODEL`` given the closet as a text list plus the same question,
  no tools, answering in a JSON schema so it can be scored. Cached on disk.
- **Arm 3** (manual, the real ChatGPT/Gemini app): ``--write-manual`` writes the 10 marked tasks
  with the closet text to paste, and a place for the owner to record the answers.

Scores per task (``score``): pieces that are not in the closet (invented), outfits that break a
rule (``engine.outfits.violations``: **Synclook's own rulebook**, so arm 1 passes it by
construction; read the per-rule detail before calling a violation wrong), items the user excluded,
"says the closet cannot do it" for the decline tasks, a suggestion already owned, and for products:
in budget, link opens (one GET, cached), title names the asked item and colour. Arm 2's titles are
its own claims, so they are checked on the page its link opens instead.

    poetry run python evaluation/head_to_head.py            # arms 1 and 2, then the report
    poetry run python evaluation/head_to_head.py --write-manual
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import agent, toolkit  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.engine.gaps import _gap, candidates  # noqa: E402
from backend.engine.outfits import ClosetItem, Outfit, Weather, _needs_footwear, valid_looks, violations  # noqa: E402
from backend.schemas.clothing import Color  # noqa: E402
from backend.schemas.taxonomy import GarmentCategory, GarmentType, Occasion  # noqa: E402
from backend.services import closet, wear  # noqa: E402
from backend.services.product_judge import ProductJudge  # noqa: E402
from backend.services.product_search import ProductSearchService  # noqa: E402
from backend.tools.product_search import ProductSearchTool  # noqa: E402
from evaluation import agent_tools  # noqa: E402

HERE = Path(__file__).resolve().parent
TASKS = HERE / "head_to_head_tasks.json"
TASKS_SHA256 = "7dee7150ef74c0c2415505770cfb458c13746581fa979a19f60265287759ea1b"  # fixed before the first run
REPORT = HERE / "head_to_head_eval.json"
MANUAL = HERE / "head_to_head_manual.md"
ARM3 = HERE / "head_to_head_arm3.json"  # the owner's arm 3 answers, transcribed by hand
CACHE_DIR = HERE / ".cache" / "head_to_head"
ARM2_MODEL = "openai/gpt-5.6-terra"
MAX_NEW_SEARCHES = 10  # plan rule: ask the owner before more SerpAPI searches than this in one run

ROWS = agent_tools.ROWS
ITEMS = [closet.engine_item(r) for r in ROWS]
NUMBER = {i.id: n for n, i in enumerate(ITEMS, 1)}  # item number = the demo file's prefix
BY_LABEL = {i.short_label: i for i in ITEMS}
assert len(BY_LABEL) == len(ITEMS), "closet labels must be unique to match names"


def load_tasks() -> list[dict[str, Any]]:
    raw = TASKS.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TASKS_SHA256:
        raise SystemExit(f"{TASKS.name} changed after it was fixed; the tasks may not drift once results are seen")
    tasks: list[dict[str, Any]] = json.loads(raw)["tasks"]
    return tasks


def closet_text() -> str:
    """The closet as a user would paste it: one line per item, the same tags Synclook stores."""
    return "\n".join(
        f"- {i.short_label} ({i.garment_type.replace('_', ' ')}, {i.color.value}, {i.pattern.replace('_', ' ')}, "
        f"{i.formality.name.lower().replace('_', ' ')}, {i.warmth.value} warmth)"
        for i in ITEMS
    )


# ──────────────────────────────────────────────────────────────────────
#  One answer shape for every arm
# ──────────────────────────────────────────────────────────────────────


@dataclass
class Answer:
    outfits: list[list[str]] = field(default_factory=list)
    """Each outfit's pieces: a closet item id when the piece is in the closet, else the text named."""
    suggestion: tuple[str, str] | None = None
    """(garment type, colour) to buy."""
    products: list[dict[str, Any]] = field(default_factory=list)
    """title, price (₹ number or None), link."""
    text: str = ""
    raw: Any = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def match(name: str) -> ClosetItem | None:
    """The closet item a free-text piece names: same label, or the longest label inside the name."""
    n = f" {_norm(name)} "
    hits = [i for label, i in BY_LABEL.items() if f" {_norm(label)} " in n]
    return max(hits, key=lambda i: len(i.short_label)) if hits else None


def price_of(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    digits = re.sub(r"[^0-9.]", "", str(value or "").replace(",", ""))
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────────────────
#  Arm 1: Synclook's agent and tools
# ──────────────────────────────────────────────────────────────────────


_OUTFIT_START = re.compile(r"(?im)^\s*(?:\d+[.)]\s|(?:\*\*)?(?:outfit|look|option)\s*#?\d+)")


def outfits_in(reply: str) -> list[list[str]]:
    """The ids of each outfit in a reply: split at "Outfit N" labels *or* numbered-list lines.

    ``toolkit.shown_outfits`` splits at labels only; replies like "1. **Olive dress [id]** …" then read
    as one outfit (3 of the 30 agent replies here).
    """
    groups = [list(dict.fromkeys(toolkit._ID.findall(p))) for p in _OUTFIT_START.split(reply)]
    return [g for g in groups if g]


class DiskCache:
    """A ``KvCache`` stand-in kept in one JSON file (no database for an eval)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}

    async def get(self, key: str) -> Any | None:
        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False))


class MemoryCache(DiskCache):
    def __init__(self) -> None:
        self._data = {}

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = value


NEW_SEARCHES = 0


async def _search(ctx: toolkit.Ctx, args: Any) -> dict[str, Any]:
    """The real ``search_products``, its whole result cached on disk (Jev scores move ±0.05 between calls)."""
    global NEW_SEARCHES
    path = CACHE_DIR / "search" / f"{hashlib.sha256(args.model_dump_json().encode()).hexdigest()}.json"
    if path.exists():
        cached: dict[str, Any] = json.loads(path.read_text())
        return cached
    if NEW_SEARCHES >= MAX_NEW_SEARCHES:
        return {"error": "eval search limit reached"}
    NEW_SEARCHES += 1
    result = await toolkit.search_products(ctx, args)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False))
    return result


TOOLS = tuple(replace(t, run=_search) if t.name == "search_products" else t for t in toolkit.TOOLS)


def _ctx(task: dict[str, Any], products: ProductSearchTool, judge: ProductJudge) -> toolkit.Ctx:
    weather = AsyncMock()
    w = task.get("weather")
    # A place named in the question gets the task's weather.
    weather.forecast = AsyncMock(return_value=Weather(**w) if w else None)
    return toolkit.Ctx(
        db=AsyncMock(), user_id=agent_tools.USER, weather=weather, products=products, judge=judge,
        cache=MemoryCache(),  # type: ignore[arg-type]  # the daily cap starts fresh per task
        today=agent_tools.TODAY,
    )  # fmt: skip


async def arm1(llm: agent_tools.CachedLLM, task: dict[str, Any], products: ProductSearchTool) -> Answer:
    ctx = _ctx(task, products, ProductJudge())
    events = [e async for e in agent.run_turn(llm, ctx, [], task["question"], tools=TOOLS)]
    reply: str = next(e["text"] for e in events if e["type"] == "reply")
    results = [(e["name"], e["result"]) for e in events if e["type"] == "tool_result"]
    ans = Answer(text=reply, raw={"reply": reply, "tools": results, "done": events[-1]})
    ans.outfits = outfits_in(reply)  # what the user sees: the ids in the reply, outfit by outfit
    searched = [r for n, r in results if n == "search_products" and "products" in r]
    asked = [
        json.loads(e["arguments"] or "{}")
        for e in events
        if e["type"] == "tool_call" and e["name"] == "search_products"
    ]
    found = [
        a
        for a, (n, r) in zip(asked, [x for x in results if x[0] == "search_products"], strict=True)
        if r.get("products")
    ]
    gaps = [r for n, r in results if n == "find_gap_item" and r.get("gaps")]
    if asked:  # what it recommends: the last search that found products (it moves on when one finds none)
        pick = (found or asked)[-1]
        ans.suggestion = (pick["garment_type"], pick["color"])
    elif gaps:
        top = gaps[-1]["gaps"][0]
        ans.suggestion = (top["garment_type"], top["color"])
    ans.products = [{**p, "price": price_of(p["price"])} for r in searched for p in r["products"]]
    return ans


# ──────────────────────────────────────────────────────────────────────
#  Arm 2: a plain chatbot
# ──────────────────────────────────────────────────────────────────────


class Look(BaseModel):
    items: list[str] = Field(description="Each piece by its name exactly as written in my closet list")
    why: str


class Buy(BaseModel):
    garment_type: GarmentType
    color: Color


class Listing(BaseModel):
    title: str
    price_inr: float | None
    link: str = Field(description="URL of the product page")


class ChatbotAnswer(BaseModel):
    outfits: list[Look] = Field(description="Outfits from my closet, best first; empty if I did not ask for one")
    buy: Buy | None = Field(description="The one item to buy, if I asked what to buy")
    products: list[Listing] = Field(description="Products I could buy, if I asked where to buy something")
    note: str = Field(description="Anything else you want to tell me")


SYSTEM = (
    "You are a helpful personal stylist. The user shares their closet and asks a question. "
    "Answer in the JSON format given."
)


def arm2_prompt(question: str) -> str:
    return f"Here is everything in my closet:\n{closet_text()}\n\n{question}"


async def arm2(client: AsyncOpenAI, task: dict[str, Any]) -> Answer:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": arm2_prompt(task["question"])}]
    schema = ChatbotAnswer.model_json_schema()
    key = json.dumps([ARM2_MODEL, messages, schema], sort_keys=True)
    path = CACHE_DIR / "arm2" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    if path.exists():
        body: dict[str, Any] = json.loads(path.read_text())
    else:
        response = await client.chat.completions.create(  # type: ignore[call-overload]
            model=ARM2_MODEL,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "ChatbotAnswer", "strict": False, "schema": schema},
            },
            max_tokens=8000,
            extra_body={"provider": {"require_parameters": True}, "usage": {"include": True}},
            timeout=180,
        )
        body = response.model_dump()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, ensure_ascii=False))
    content = body["choices"][0]["message"]["content"] or ""
    try:
        parsed = ChatbotAnswer.model_validate_json(content)
    except ValueError:
        return Answer(text=content, raw=body)  # unparseable: scored as no answer
    return Answer(
        outfits=[[(m.id if (m := match(p)) else p) for p in look.items] for look in parsed.outfits],
        suggestion=(parsed.buy.garment_type.value, parsed.buy.color.value) if parsed.buy else None,
        products=[{"title": p.title, "price": p.price_inr, "link": p.link} for p in parsed.products],
        text=" ".join([parsed.note, *(look.why for look in parsed.outfits)]),
        raw={"answer": parsed.model_dump(mode="json"), "usage": body.get("usage")},
    )


# ──────────────────────────────────────────────────────────────────────
#  Checks on product links (one GET each, cached)
# ──────────────────────────────────────────────────────────────────────

_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)|<title[^>]*>([^<]+)</title>', re.I
)
_SEARCHY = re.compile(r"[?&](q|k|query|rawQuery|search)=|/search\b|/s\?", re.I)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"


async def open_link(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    path = CACHE_DIR / "links" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    if path.exists():
        cached: dict[str, Any] = json.loads(path.read_text())
        return cached
    try:
        r = await client.get(url)
        found = _TITLE.search(r.text[:400_000])
        title = html.unescape(next(g for g in found.groups() if g)).strip() if found else ""
        out = {"status": r.status_code, "final_url": str(r.url), "page_title": title}
    except (httpx.HTTPError, ValueError) as exc:
        out = {"status": None, "final_url": url, "page_title": "", "error": type(exc).__name__}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False))
    return out


# shortcut: a few synonyms per word, by hand; widen if a correct title is scored as a miss.
_ALIASES = {
    "sneakers": ["sneaker", "trainer", "running shoe", "casual shoe"],
    "boots": ["boot"],
    "chinos": ["chino", "trouser", "pant"],
    "trousers": ["trouser", "pant"],
    "t_shirt": ["t shirt", "tshirt", "tee"],
    "jacket": ["jacket"],
    "loafers": ["loafer"],
    "beige": ["beige", "khaki", "sand", "cream", "tan", "stone"],
    "white": ["white", "off white"],
    "navy": ["navy"],
}


def names_item(title: str, garment_type: str, color: str) -> bool:
    t = f" {_norm(title)} "
    words = _ALIASES.get(garment_type, [garment_type.replace("_", " ").rstrip("s")])
    colours = _ALIASES.get(color, [color])
    return any(f" {w}" in t for w in words) and any(f" {c} " in t or f" {c}" in t for c in colours)


# ──────────────────────────────────────────────────────────────────────
#  Scoring
# ──────────────────────────────────────────────────────────────────────

_NEGATION = re.compile(
    r"\b(no|not|(do|does|ca|is|are)n['’]t|do not|does not|lack|lacks|missing|without|cannot|none)\b",
    re.I,
)
_ERROR_PAGE = re.compile(r"not found|\b404\b|access denied|error", re.I)
_NOT_FOR_MEN = {"dress", "skirt", "blouse", "lehenga", "saree", "gown", "anarkali"}


def new_outfits(suggestion: tuple[str, str], buyer: str) -> int | None:
    """Synclook's own count of new outfits the purchase unlocks (None: not one of its ≤39 candidates)."""
    items = sorted(ITEMS, key=lambda i: i.id)
    cand = next((c for c in candidates(items, buyer) if (c.garment_type, c.color_family) == suggestion), None)
    if cand is None:
        return None
    had = {o for o in Occasion if valid_looks(items, o).looks}
    gap = _gap(items, cand, had)
    return gap.new_outfits if gap else 0


def incomplete(items: tuple[ClosetItem, ...], occasion: Occasion, problems: list[str]) -> list[str]:
    """The rule breaks anyone would call wrong (no shoes, no bottom, a tee alone in the cold), as opposed to
    Synclook's style rules (colour policy, formality range, one outerwear, its list of known pairings)."""
    cats = {i.category for i in items}
    out = []
    if GarmentCategory.FULLBODY not in cats and not {GarmentCategory.TOPWEAR, GarmentCategory.BOTTOMWEAR} <= cats:
        out.append("no top + bottom or one-piece")
    if _needs_footwear(occasion) and GarmentCategory.FOOTWEAR not in cats:
        out.append("no footwear")
    return out + [p for p in problems if p.endswith("too light without a layer")]


def score(task: dict[str, Any], ans: Answer, links: dict[str, dict[str, Any]]) -> dict[str, Any]:
    kind = task["kind"]
    out: dict[str, Any] = {"id": task["id"], "kind": kind}
    by_id = {i.id: i for i in ITEMS}
    if kind in {"outfit", "exclude", "decline"}:
        occasion = Occasion(task["occasion"])
        weather = Weather(**task["weather"]) if task.get("weather") else None
        banned = set(task.get("exclude", []))
        pieces = [p for look in ans.outfits for p in look]
        invented = [p for p in pieces if p not in by_id]
        per_look = []
        for look in ans.outfits:
            items = tuple(by_id[p] for p in look if p in by_id)
            problems = violations(Outfit(items, 0.0, {}, ()), occasion, weather)
            excluded = [by_id[p].short_label for p in look if p in by_id and NUMBER[p] in banned]
            fake = [p for p in look if p not in by_id]
            per_look.append({
                "violations": problems, "incomplete": incomplete(items, occasion, problems),
                "excluded_used": excluded, "invented": fake,
            })  # fmt: skip
        out |= {
            "outfits": len(ans.outfits),
            "pieces": len(pieces),
            "invented": len(invented),
            "invented_names": invented,
            "outfits_with_violation": sum(bool(x["violations"]) for x in per_look),
            "outfits_incomplete": sum(bool(x["incomplete"]) for x in per_look),
            "outfits_using_excluded": sum(bool(x["excluded_used"]) for x in per_look),
            "valid_outfits": sum(not (x["violations"] or x["excluded_used"] or x["invented"]) for x in per_look),
            "looks": per_look,
        }
        all_valid = out["valid_outfits"] == len(ans.outfits)
        # Without Synclook's style rules: only invented, excluded and incomplete outfits count against it.
        all_sound = not any(x["incomplete"] or x["excluded_used"] or x["invented"] for x in per_look)
        if kind == "decline":
            flagged = bool(re.search(task["missing"], ans.text, re.I) and _NEGATION.search(ans.text))
            out["says_closet_cannot"] = flagged
            out["pass"], out["pass_hard"] = flagged and all_valid, flagged and all_sound
        else:
            out["pass"], out["pass_hard"] = bool(ans.outfits) and all_valid, bool(ans.outfits) and all_sound
        return out

    if kind in {"gap", "gap_products"}:
        owned = {(i.garment_type, i.color_family) for i in ITEMS} | {(i.garment_type, i.color.value) for i in ITEMS}
        buyer = task.get("buyer", "all")
        s = ans.suggestion
        out |= {
            "suggestion": " ".join(s) if s else None,
            "already_owned": bool(s and s in owned),
            "fits_buyer": bool(s and not (buyer == "menswear" and s[0] in _NOT_FOR_MEN)),
            "new_outfits_by_synclook_count": new_outfits(s, buyer) if s else None,
        }
        out["pass"] = bool(s) and not out["already_owned"] and out["fits_buyer"]
    want = task.get("want") or (
        {"garment_type": ans.suggestion[0], "color": ans.suggestion[1]} if ans.suggestion else None
    )
    if kind in {"products", "gap_products"}:
        budget = task["budget"]
        rows = []
        for p in ans.products:
            link = links.get(p["link"], {}) if p["link"] else {}
            status = link.get("status")
            # Arm 1's titles are the shop's own listing data; arm 2's are its claim, so check the page it links.
            title = p["title"] if p.get("from_listing") else link.get("page_title", "")
            rows.append({
                "title": p["title"],
                "page_title": link.get("page_title"),
                "price": p["price"],
                "link": p["link"],
                "status": status,
                "in_budget": p["price"] is not None and p["price"] <= budget,
                # A 200 can still be an error page ("Page Not Found", "Access Denied").
                # None = no link given (arm 3's shopping cards): reported, not failed.
                "opens": None if not p["link"] else (
                    status is not None and status < 400 and not _ERROR_PAGE.search(link.get("page_title", ""))
                ),
                "search_page": bool(p["link"] and _SEARCHY.search(p["link"])),
                "title_matches": bool(want and title and names_item(title, want["garment_type"], want["color"])),
                "claimed_title_matches": bool(want and names_item(p["title"], want["garment_type"], want["color"])),
            })  # fmt: skip
        n = len(rows)
        out |= {
            "products": n,
            "in_budget": sum(r["in_budget"] for r in rows),
            "opens": sum(r["opens"] is True for r in rows),
            "links_not_given": sum(r["opens"] is None for r in rows),
            "search_pages": sum(r["search_page"] for r in rows),
            "title_matches": sum(r["title_matches"] for r in rows),
            "rows": rows,
        }
        good = n > 0 and all(r["in_budget"] and r["opens"] is not False and r["title_matches"] for r in rows)
        out["pass"] = good and out.get("pass", True)
    out.setdefault("pass_hard", out["pass"])  # shopping has no style rules: one pass rule
    return out


# ──────────────────────────────────────────────────────────────────────
#  Report
# ──────────────────────────────────────────────────────────────────────


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def total(key: str) -> int:
        return sum(int(r.get(key) or 0) for r in rows)

    outfit_rows = [r for r in rows if "outfits" in r]
    return {
        "tasks_passed": sum(r["pass"] for r in rows),
        "tasks_passed_without_style_rules": sum(r["pass_hard"] for r in rows),
        "tasks": len(rows),
        "pieces_named": total("pieces"),
        "invented_pieces": total("invented"),
        "outfits": total("outfits"),
        "outfits_with_violation": total("outfits_with_violation"),
        "outfits_incomplete": total("outfits_incomplete"),
        "outfits_using_excluded": total("outfits_using_excluded"),
        "valid_outfits": total("valid_outfits"),
        "outfit_tasks_with_an_outfit": sum(r["outfits"] > 0 for r in outfit_rows if r["kind"] != "decline"),
        "declines_flagged": sum(bool(r.get("says_closet_cannot")) for r in rows),
        "suggestions_already_owned": sum(bool(r.get("already_owned")) for r in rows),
        "products": total("products"),
        "products_in_budget": total("in_budget"),
        "products_link_opens": total("opens"),
        "products_link_not_given": total("links_not_given"),
        "products_title_matches": total("title_matches"),
    }


def arm3() -> dict[str, Answer]:
    """The owner's app answers: outfits/products as transcribed (``ARM3``), the text straight from ``MANUAL``."""
    if not ARM3.exists():
        return {}
    texts = dict(re.findall(r"(?ms)^## \d+\. `(\w+)`\n(.*?)(?=^## |\Z)", MANUAL.read_text()))
    out = {}
    for task_id, a in json.loads(ARM3.read_text())["answers"].items():
        out[task_id] = Answer(
            outfits=[[(m.id if (m := match(p)) else p) for p in look] for look in a.get("outfits", [])],
            suggestion=tuple(a["suggestion"]) if a.get("suggestion") else None,
            # Shopping cards: listing titles from the app's shop index, so checked as is (like arm 1's).
            products=[{**p, "link": None, "from_listing": True} for p in a.get("products", [])],
            text=texts[task_id],
            raw={"transcribed": a},
        )
    return out


def write_manual(tasks: list[dict[str, Any]]) -> None:
    if MANUAL.exists() and MANUAL.read_text().count("_pending_") < sum(bool(t.get("manual")) for t in tasks):
        raise SystemExit(f"{MANUAL.name} already holds the owner's answers; not overwriting it")
    picked = [t for t in tasks if t.get("manual")]
    lines = [
        "# Head-to-head, arm 3: the real chatbot app (manual)",
        "",
        "**Status: pending on the owner.** Generated by `evaluation/head_to_head.py --write-manual` from the fixed",
        f"tasks (`head_to_head_tasks.json`, SHA-256 `{TASKS_SHA256[:12]}…`).",
        "",
        "How: open a **new chat** for each task in ChatGPT (or Gemini), default model, web search left on if the app",
        "turns it on by itself. Paste the closet block, then the task's question, in one message. Copy the answer",
        "under the task. Note the app, model and date once at the top. Scoring is by the same rules as arms 1 and 2",
        "(pieces not in the closet, rule breaks, excluded items, says the closet cannot, budget, links).",
        "",
        "App / model / date: _____",
        "",
        "## Closet (paste this first, as is)",
        "",
        "```",
        "Here is everything in my closet:",
        closet_text(),
        "```",
        "",
    ]
    for n, t in enumerate(picked, 1):
        lines += [f"## {n}. `{t['id']}`", "", f"**Question:** {t['question']}", "", "**Answer:**", "", "_pending_", ""]
    MANUAL.write_text("\n".join(lines))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="Run only these task ids")
    parser.add_argument("--arm", choices=["1", "2", "both"], default="both")
    parser.add_argument("--write-manual", action="store_true", help="Write the arm 3 sheet and stop")
    args = parser.parse_args()
    tasks = load_tasks()
    if args.write_manual:
        write_manual(tasks)
        print(f"wrote {MANUAL.relative_to(PROJECT_ROOT)}")
        return
    if args.only:
        tasks = [t for t in tasks if t["id"] in args.only]

    closet.list_items = agent_tools._list_items  # type: ignore[assignment]
    wear.events = agent_tools._events  # type: ignore[assignment]
    wear.record = agent_tools._record  # type: ignore[assignment]
    settings = get_settings()
    llm = agent_tools.CachedLLM(settings)
    products = ProductSearchTool(ProductSearchService(), DiskCache(CACHE_DIR / "kv.json"))  # type: ignore[arg-type]
    client = AsyncOpenAI(api_key=settings.vlm_api_key, base_url=settings.vlm_base_url)

    answers: dict[str, dict[str, Answer]] = {"synclook": {}, "chatbot": {}, "chatbot_app": arm3()}
    for t in tasks:
        agent_tools.LOG.clear()
        if args.arm in {"1", "both"}:
            answers["synclook"][t["id"]] = a = await arm1(llm, t, products)
            for p in a.products:
                p["from_listing"] = True
        if args.arm in {"2", "both"}:
            answers["chatbot"][t["id"]] = await arm2(client, t)
        print(f"  {t['id']}: done", flush=True)

    urls = {p["link"] for arm in answers.values() for a in arm.values() for p in a.products if p["link"]}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers={"User-Agent": UA}) as http:
        links = dict(zip(urls, await asyncio.gather(*(open_link(http, u) for u in urls)), strict=True))

    report: dict[str, Any] = {
        "tasks_sha256": TASKS_SHA256,
        "arms": {
            "synclook": f"agent on {settings.agent_model} + Synclook tools",
            "chatbot": f"{ARM2_MODEL}, no tools",
            "chatbot_app": "the owner in a real chatbot app (not stated which), 10 tasks, transcribed by hand",
        },
        "date": str(dt.date.today()),
        "new_model_calls_arm1": agent_tools.CachedLLM.calls,
        "new_searches_arm1": NEW_SEARCHES,
    }
    for arm, by_task in answers.items():
        if not by_task:
            continue
        rows = [
            score(t, by_task[t["id"]], links) | {"answer": by_task[t["id"]].raw} for t in tasks if t["id"] in by_task
        ]
        report[arm] = {"summary": summary(rows), "tasks": rows}
        print(arm, json.dumps(report[arm]["summary"]))
    if not args.only and args.arm == "both":
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
        print(f"wrote {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
