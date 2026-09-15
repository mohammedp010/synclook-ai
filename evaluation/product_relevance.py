"""Offline product-relevance evaluation for the shopping matchers.

Runs the ShoppingAgent's product scoring over hand-labeled fixtures
(``product_cases.json``) and reports precision / recall / F1 of the
"keep vs drop" decision against the labels, for both matchers:

- ``keyword``: legacy title-token matching (no models needed)
- ``embedding``: CLIP similarity to the desired-item spec (loads CLIP;
  fixture thumbnails are fake, so this measures the title-text component)

Usage::

    poetry run python evaluation/product_relevance.py              # both matchers
    poetry run python evaluation/product_relevance.py --matcher keyword
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.shopping_agent import ShoppingAgent  # noqa: E402
from backend.schemas.api import ProductLink  # noqa: E402
from evaluation.recording import record_if_asked  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "product_cases.json"


async def evaluate_product_relevance(cases_path: Path = CASES_PATH, matcher: str = "keyword") -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    agent = ShoppingAgent(product_tool=None)

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

        if matcher == "embedding":
            kept = await agent._validate_products_embedding(
                list(products),
                allowed_item_type=desired["item_type"],
                color=desired["color"],
                style=desired["style"],
                shopping_intent=desired["shopping_intent"],
            )
        else:
            kept = agent._validate_products_keyword(
                list(products),
                allowed_item_type=desired["item_type"],
                color=desired["color"],
                style=desired["style"],
                shopping_intent=desired["shopping_intent"],
            )
        kept_titles = {p.title for p in kept}

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
                "kept": len(kept),
                "false_positives": case_fp,
                "false_negatives": case_fn,
            }
        )

    precision = true_pos / max(true_pos + false_pos, 1)
    recall = true_pos / max(true_pos + false_neg, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    return {
        "summary": {
            "num_cases": len(cases),
            "num_products": true_pos + false_pos + false_neg + true_neg,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "matcher": matcher,
        },
        "cases": case_reports,
    }


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="Evaluate shopping product-relevance matchers")
    parser.add_argument("--matcher", choices=["keyword", "embedding", "both"], default="both")
    parser.add_argument("--record", action="store_true", help="persist the run to PostgreSQL")
    args = parser.parse_args()

    matchers = ["keyword", "embedding"] if args.matcher == "both" else [args.matcher]
    reports = {}
    for matcher in matchers:
        reports[matcher] = await evaluate_product_relevance(matcher=matcher)
    print(json.dumps(reports, indent=2))

    # One row per matcher: they are alternative implementations of the same
    # stage, and a chart that averaged them would hide the comparison that is
    # the whole point of keeping the keyword baseline around.
    for matcher, report in reports.items():
        await record_if_asked(
            args.record,
            f"product_relevance:{matcher}",
            num_cases=report["summary"]["num_cases"],
            metrics=report["summary"],
        )


if __name__ == "__main__":
    asyncio.run(main())
