"""Offline product-relevance evaluation for the shopping matchers.

Runs the product gate over hand-labeled fixtures and reports precision /
recall / F1 of the "keep vs drop" decision against the labels, per matcher:

- ``keyword``: title-token matching, the baseline (no models needed; lives here
  only, since the live path never uses it)
- ``jev``: the live gate, ``services.product_judge.gate`` — buyer policy in code,
  then Jev's item / colour / buyer nouls in one batched call per slot (needs JEV_API_KEY)
- ``jev_isolated``: the same nouls, one call per product, so no title is a
  distractor for another (reference §8.5)

The CLIP matcher it once compared against (F1 0.893 calibration, 0.469
held-out) was removed with CLIP in the closet-first redesign.

Two case files. ``product_cases.json`` (53 products) is the set the old CLIP
matcher was calibrated on.
``product_cases_heldout.json`` (126 products, 21 slots, 14 of them concrete
accessories) was written for Phase 6 *before* any arm ran on it, and is full of
hard negatives: belt bags, watch straps, tie clips, kids' sizes, neighbouring
colours (ivory for white, olive for green). Its labels are mine — model-made,
like the ``public`` perception split — and follow the original file's rules: a
product is relevant iff it is the item itself, in the wanted colour or a shade
of it, for the wanted buyer.

Usage::

    poetry run python evaluation/product_relevance.py                       # keyword (no keys)
    poetry run python evaluation/product_relevance.py --matcher all --cases heldout
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.api import ProductLink  # noqa: E402
from backend.schemas.taxonomy import AccessoryType  # noqa: E402
from backend.services.product_judge import ProductJudge, ProductVerdict, Wanted, gate  # noqa: E402
from backend.tools.accessory_rules import accessory_name, as_accessory  # noqa: E402
from backend.tools.style_rules import INVALID_ITEMS_BY_SHOPPING_INTENT, normalize_shopping_intent  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "product_cases.json"
CASE_FILES = {"calibration": CASES_PATH, "heldout": Path(__file__).resolve().parent / "product_cases_heldout.json"}
MATCHERS = ("keyword", "jev", "jev_isolated")
SWEEP = (0.3, 0.4, 0.5, 0.6, 0.7)

# ── Keyword baseline (the old shopping agent's title matcher, moved here in Phase 4) ──

MIN_KEYWORD_SCORE = 0.5
_ACCESSORY_KEYWORDS: dict[AccessoryType, set[str]] = {
    AccessoryType.TOTE_BAG: {"tote"},
    AccessoryType.CROSSBODY_BAG: {"crossbody", "cross body", "sling bag"},
    AccessoryType.BRIEFCASE: {"briefcase", "laptop bag", "office bag"},
    AccessoryType.RINGS: {"ring"},
    AccessoryType.SUNGLASSES: {"sunglasses", "shades"},
    AccessoryType.STOLE: {"stole", "shawl"},
}
_ITEM_SYNONYMS = {
    "t-shirt": {"t-shirt", "tshirt", "tee"},
    "trousers": {"trousers", "pants"},
    "hoodie": {"hoodie", "hooded"},
    "sweater": {"sweater", "pullover"},
    "jeans": {"jeans", "denim"},
    "shoes": {"shoes", "sneakers", "footwear", "boots", "loafers"},
    "accessory": {"accessory", "belt", "watch", "bag", "scarf", "cap"},
}
_COLOUR_SYNONYMS = {
    "grey": {"grey", "gray"},
    "navy": {"navy", "dark blue"},
    "cream": {"cream", "off white", "off-white"},
}


def _item_keywords(item_type: str) -> set[str]:
    accessory = as_accessory(item_type)
    if accessory is not None:
        return _ACCESSORY_KEYWORDS.get(accessory, {accessory_name(accessory)})
    allowed = (item_type or "").strip().lower().replace("_", "-")
    return _ITEM_SYNONYMS.get(allowed, {allowed}) if allowed else set()


def keyword_keeps(title: str, *, item_type: str, color: str, style: str, shopping_intent: str) -> bool:
    """Item word required (0.5), then colour, style, image, price and seller add points; keep at ≥ 0.5.

    The fixtures have no image or price fields that differ by relevance, so in practice the
    decision is: the buyer policy passes and the title names the item."""
    title = title.lower()
    invalid = INVALID_ITEMS_BY_SHOPPING_INTENT.get(normalize_shopping_intent(shopping_intent), set())
    if not title or any(t.value in title for t in invalid):
        return False
    words = _item_keywords(item_type)
    if words and not any(w in title for w in words):
        return False
    colour = (color or "").strip().lower()
    style_words = {s := (style or "").strip().lower().replace("_", " "), *s.split()} if style else set()
    score = 0.5
    score += 0.15 if colour and any(w in title for w in _COLOUR_SYNONYMS.get(colour, {colour})) else 0
    score += 0.1 if style_words and any(w in title for w in style_words) else 0
    return score >= MIN_KEYWORD_SCORE


class _RecordingJudge(ProductJudge):
    """Keeps every verdict and call latency, so the eval can sweep the bar offline."""

    def __init__(self, *, batched: bool) -> None:
        super().__init__(batched=batched)
        self.verdicts: dict[str, ProductVerdict] = {}
        self.latencies_ms: list[float] = []

    async def judge(self, wanted: Wanted, titles: list[str]) -> list[ProductVerdict]:
        started = time.perf_counter()
        verdicts = await super().judge(wanted, titles)
        self.latencies_ms.append((time.perf_counter() - started) * 1000)
        self.verdicts.update(zip(titles, verdicts))
        return verdicts


async def evaluate_product_relevance(cases_path: Path = CASES_PATH, matcher: str = "keyword") -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    judge = _RecordingJudge(batched=matcher != "jev_isolated") if "jev" in matcher else None
    labelled: list[tuple[str, bool]] = []

    true_pos = false_pos = false_neg = true_neg = 0
    case_reports: list[dict[str, Any]] = []

    for case in cases:
        desired = case["desired"]
        products = [
            ProductLink(
                title=p["title"],
                price=p.get("price", ""),
                link="https://example.com/product",
                thumbnail=p.get("thumbnail", ""),
                source=p.get("source", ""),
            )
            for p in case["products"]
        ]
        labels = [bool(p["relevant"]) for p in case["products"]]
        labelled.extend((p.title, rel) for p, rel in zip(products, labels))
        if judge is not None:
            wanted = Wanted(
                item=desired["item_type"].replace("_", " "),
                colour=desired["color"],
                shopping_intent=normalize_shopping_intent(desired["shopping_intent"]),
            )
            kept_titles = {p.title for p in await gate(judge, products, wanted)}
        else:
            kept_titles = {
                p.title
                for p in products
                if keyword_keeps(
                    p.title,
                    item_type=desired["item_type"],
                    color=desired["color"],
                    style=desired["style"],
                    shopping_intent=desired["shopping_intent"],
                )
            }

        case_tp = case_fp = case_fn = 0
        for product, relevant in zip(products, labels):
            predicted = product.title in kept_titles
            if predicted and relevant:
                true_pos += 1
                case_tp += 1
            elif predicted and not relevant:
                false_pos += 1
                case_fp += 1
            elif not predicted and relevant:
                false_neg += 1
                case_fn += 1
            else:
                true_neg += 1

        case_reports.append(
            {
                "name": case["name"],
                "kept": len(kept_titles),
                "false_positives": case_fp,
                "false_negatives": case_fn,
                "wrong": [p.title for p, rel in zip(products, labels) if (p.title in kept_titles) != rel],
            }
        )

    precision, recall, f1 = _prf(true_pos, false_pos, false_neg)
    summary: dict[str, Any] = {
        "num_cases": len(cases),
        "num_products": true_pos + false_pos + false_neg + true_neg,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matcher": matcher,
    }
    report: dict[str, Any] = {"summary": summary, "cases": case_reports}
    if judge is not None and judge.latencies_ms:
        summary["median_call_ms"] = round(sorted(judge.latencies_ms)[len(judge.latencies_ms) // 2])
        summary["calls"] = len(judge.latencies_ms)
        # The bar if it were elsewhere — printed, not acted on (labels are model-made).
        report["threshold_sweep"] = {
            str(bar): round(_prf(*_counts(judge.verdicts, labelled, bar))[2], 4) for bar in SWEEP
        }
    return report


def _counts(verdicts: dict[str, ProductVerdict], labelled: list[tuple[str, bool]], bar: float) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for title, relevant in labelled:
        v = verdicts.get(title)
        kept = v is not None and min(v.p_item, v.p_colour, v.p_buyer) >= bar
        tp += kept and relevant
        fp += kept and not relevant
        fn += relevant and not kept
    return tp, fp, fn


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return precision, recall, 2 * precision * recall / max(precision + recall, 1e-9)


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="Evaluate shopping product-relevance matchers")
    parser.add_argument("--matcher", choices=[*MATCHERS, "all"], default="keyword")
    parser.add_argument("--cases", choices=sorted(CASE_FILES), default="calibration")
    args = parser.parse_args()

    matchers = list(MATCHERS) if args.matcher == "all" else [args.matcher]
    reports = {}
    for matcher in matchers:
        reports[matcher] = await evaluate_product_relevance(CASE_FILES[args.cases], matcher=matcher)
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
