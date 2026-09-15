"""Evaluation harness for deterministic recommendation quality metrics.

Metrics
-------
Policy metrics (no ground truth needed — checked against product policy):
- ``invalid_item_rate``: recommended items on a case's forbidden list
- ``intent_mismatch_rate``: items violating the shopping-intent policy
- ``empty_recommendation_rate``: cases that produced zero recommendations
- ``complete_outfit_rate``: recommendations satisfying the outfit-structure
  contract (every required category present) — via ``get_outfit_structure``
- ``duplicate_item_rate``: recommendations containing duplicate item types

Golden metrics (require hand-labeled ``expected`` lists; golden cases only):
- ``recommendation_consistency_error_rate``: items outside the expected set

Latency:
- per-agent timings aggregated across cases (mean / p95)

Usage::

    poetry run python evaluation/harness.py            # print report
    poetry run python evaluation/harness.py --check    # exit 1 on regression
    poetry run python evaluation/harness.py --record   # persist EvaluationRun
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

# Allow running this file directly via `python evaluation/harness.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.base import AgentContext  # noqa: E402
from backend.agents.recommendation_agent import RecommendationAgent  # noqa: E402
from backend.agents.styling_agent import StylingAgent  # noqa: E402
from backend.schemas.clothing import ClothingAttributes, ClothingType, Color, Pattern, Style  # noqa: E402
from backend.tools.style_rules import CLOTHING_TYPE_CATEGORIES, StyleRuleEngineTool  # noqa: E402
from evaluation.recording import record_if_asked  # noqa: E402

# Regression gates for --check. Golden consistency keeps its Step 23 target;
# structural gates are set from the calibrated baseline (see Progress.md).
THRESHOLDS = {
    "invalid_item_rate": 0.0,
    "intent_mismatch_rate": 0.0,
    "recommendation_consistency_error_rate": 0.1,
    "empty_recommendation_rate": 0.05,
    "duplicate_item_rate": 0.0,
    # complete_outfit_rate is a floor, not a ceiling.
    "complete_outfit_rate_min": 0.90,
}


@dataclass
class CaseResult:
    name: str
    kind: str
    invalid_item_hits: int = 0
    intent_mismatch_hits: int = 0
    consistency_hits: int = 0
    consistency_items: int = 0
    total_items: int = 0
    num_recommendations: int = 0
    complete_outfits: int = 0
    duplicate_recs: int = 0
    agent_timings: dict[str, float] = field(default_factory=dict)


def _to_attrs(case_input: dict[str, Any]) -> ClothingAttributes:
    return ClothingAttributes(
        clothing_type=ClothingType(case_input["clothing_type"]),
        primary_color=Color(case_input["primary_color"]),
        pattern=Pattern(case_input.get("pattern", "solid")),
        style=Style(case_input["style"]),
        confidence=float(case_input.get("confidence", 0.8)),
        description=case_input.get("description", ""),
    )


def _outfit_is_complete(
    style_tool: StyleRuleEngineTool,
    base_type: ClothingType,
    rec_item_types: list[str],
) -> bool:
    """A look is complete when every required category is covered.

    The base garment covers its own category; recommended items must cover the
    rest of the ``required`` list from the outfit-structure contract.
    """
    structure = style_tool.get_outfit_structure(base_type)
    required = set(structure.get("required", []))

    covered = {CLOTHING_TYPE_CATEGORIES.get(base_type, "topwear")}
    for item_type in rec_item_types:
        ct = _to_clothing_type(item_type)
        if ct is not None:
            covered.add(CLOTHING_TYPE_CATEGORIES.get(ct, "topwear"))

    return required.issubset(covered)


def _to_clothing_type(item_type: str) -> ClothingType | None:
    normalized = item_type.strip().lower()
    for ct in ClothingType:
        if ct.value == normalized:
            return ct
    return None


async def _run_case(
    case: dict[str, Any],
    styling: StylingAgent,
    recommendation: RecommendationAgent,
    style_tool: StyleRuleEngineTool,
) -> CaseResult:
    attrs = _to_attrs(case["input"])
    intent = case["input"].get("gender", "unisex")

    ctx = AgentContext(image_bytes=b"evaluation", gender=intent, shopping_intent=intent)
    ctx.clothing_attributes = attrs

    ctx = await styling.run(ctx)
    ctx = await recommendation.run(ctx)

    forbidden = {item.strip().lower() for item in case.get("forbidden", [])}
    expected = {item.strip().lower() for item in case.get("expected", [])}

    result = CaseResult(
        name=case["name"],
        kind=case.get("kind", "golden"),
        num_recommendations=len(ctx.recommendations),
        agent_timings=dict(ctx.agent_timings),
    )

    for rec in ctx.recommendations:
        rec_item_types = [item.item_type.strip().lower() for item in rec.items]
        result.total_items += len(rec_item_types)

        if len(set(rec_item_types)) != len(rec_item_types):
            result.duplicate_recs += 1

        if _outfit_is_complete(style_tool, attrs.clothing_type, rec_item_types):
            result.complete_outfits += 1

        for item_type in rec_item_types:
            if item_type in forbidden:
                result.invalid_item_hits += 1
            if not style_tool.is_item_allowed_for_gender(item_type, intent):
                result.intent_mismatch_hits += 1
            if expected:
                result.consistency_items += 1
                if item_type not in expected:
                    result.consistency_hits += 1

    return result


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


async def evaluate_cases(cases_path: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    styling = StylingAgent()
    recommendation = RecommendationAgent(llm_service=None)
    style_tool = StyleRuleEngineTool()

    results: list[CaseResult] = []
    for case in cases:
        results.append(await _run_case(case, styling, recommendation, style_tool))

    total_items = max(sum(r.total_items for r in results), 1)
    total_recs = max(sum(r.num_recommendations for r in results), 1)
    consistency_items = max(sum(r.consistency_items for r in results), 1)

    per_agent_latencies: dict[str, list[float]] = {}
    for r in results:
        for agent, elapsed in r.agent_timings.items():
            per_agent_latencies.setdefault(agent, []).append(elapsed)

    summary = {
        "num_cases": len(results),
        "num_golden_cases": sum(1 for r in results if r.kind == "golden"),
        "total_items_evaluated": total_items,
        "total_recommendations": total_recs,
        "invalid_item_rate": round(sum(r.invalid_item_hits for r in results) / total_items, 4),
        "intent_mismatch_rate": round(sum(r.intent_mismatch_hits for r in results) / total_items, 4),
        "recommendation_consistency_error_rate": round(sum(r.consistency_hits for r in results) / consistency_items, 4),
        "empty_recommendation_rate": round(
            sum(1 for r in results if r.num_recommendations == 0) / max(len(results), 1), 4
        ),
        "complete_outfit_rate": round(sum(r.complete_outfits for r in results) / total_recs, 4),
        "duplicate_item_rate": round(sum(r.duplicate_recs for r in results) / total_recs, 4),
        "latency_s": {
            agent: {
                "mean": round(mean(values), 4),
                "p95": round(_percentile(values, 95), 4),
            }
            for agent, values in sorted(per_agent_latencies.items())
        },
    }

    failing_cases = [
        {
            "name": r.name,
            "kind": r.kind,
            "invalid_item_hits": r.invalid_item_hits,
            "intent_mismatch_hits": r.intent_mismatch_hits,
            "consistency_hits": r.consistency_hits,
            "num_recommendations": r.num_recommendations,
            "complete_outfits": r.complete_outfits,
            "total_items": r.total_items,
        }
        for r in results
        if r.invalid_item_hits
        or r.intent_mismatch_hits
        or r.consistency_hits
        or r.duplicate_recs
        or r.num_recommendations == 0
        or r.complete_outfits < r.num_recommendations
    ]

    return {"summary": summary, "failing_cases": failing_cases}


def check_thresholds(summary: dict[str, Any]) -> list[str]:
    """Return a list of human-readable gate violations (empty = pass)."""
    violations: list[str] = []
    for metric in (
        "invalid_item_rate",
        "intent_mismatch_rate",
        "recommendation_consistency_error_rate",
        "empty_recommendation_rate",
        "duplicate_item_rate",
    ):
        if summary[metric] > THRESHOLDS[metric]:
            violations.append(f"{metric}={summary[metric]} exceeds threshold {THRESHOLDS[metric]}")
    if summary["complete_outfit_rate"] < THRESHOLDS["complete_outfit_rate_min"]:
        violations.append(
            f"complete_outfit_rate={summary['complete_outfit_rate']} "
            f"below floor {THRESHOLDS['complete_outfit_rate_min']}"
        )
    return violations


async def main() -> None:
    from backend.core.logging import setup_logging

    # Keep stdout parseable — agent info/warning logs would interleave with the JSON report.
    setup_logging("ERROR")

    parser = argparse.ArgumentParser(description="Run the recommendation evaluation harness")
    parser.add_argument("--cases", type=Path, default=Path(__file__).resolve().parent / "test_cases.json")
    parser.add_argument("--check", action="store_true", help="exit non-zero if any regression gate fails")
    parser.add_argument("--record", action="store_true", help="persist the run to PostgreSQL")
    args = parser.parse_args()

    report = await evaluate_cases(args.cases)
    print(json.dumps(report, indent=2))

    await record_if_asked(args.record, "harness", num_cases=report["summary"]["num_cases"], metrics=report["summary"])

    if args.check:
        violations = check_thresholds(report["summary"])
        if violations:
            print("\nEVAL GATE FAILED:", file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
            raise SystemExit(1)
        print("\neval gate passed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
