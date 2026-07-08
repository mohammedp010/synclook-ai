"""Evaluation harness for deterministic recommendation quality metrics."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow running this file directly via `python evaluation/harness.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.base import AgentContext  # noqa: E402
from backend.agents.recommendation_agent import RecommendationAgent  # noqa: E402
from backend.agents.styling_agent import StylingAgent  # noqa: E402
from backend.schemas.clothing import ClothingAttributes, ClothingType, Color, Pattern, Style  # noqa: E402
from backend.tools.style_rules import StyleRuleEngineTool  # noqa: E402


@dataclass
class CaseResult:
    name: str
    invalid_item_hits: int
    gender_mismatch_hits: int
    consistency_hits: int
    total_items: int


def _to_attrs(case_input: dict[str, Any]) -> ClothingAttributes:
    return ClothingAttributes(
        clothing_type=ClothingType(case_input["clothing_type"]),
        primary_color=Color(case_input["primary_color"]),
        pattern=Pattern(case_input.get("pattern", "solid")),
        style=Style(case_input["style"]),
        confidence=float(case_input.get("confidence", 0.8)),
        description=case_input.get("description", ""),
    )


async def _run_case(case: dict[str, Any]) -> CaseResult:
    attrs = _to_attrs(case["input"])
    gender = case["input"].get("gender", "unisex")

    ctx = AgentContext(image_bytes=b"evaluation", gender=gender)
    ctx.clothing_attributes = attrs

    styling = StylingAgent()
    recommendation = RecommendationAgent(llm_service=None)

    ctx = await styling.run(ctx)
    ctx = await recommendation.run(ctx)

    style_tool = StyleRuleEngineTool()
    forbidden = {item.strip().lower() for item in case.get("forbidden", [])}
    expected = {item.strip().lower() for item in case.get("expected", [])}

    all_items = [rec_item for rec in ctx.recommendations for rec_item in rec.items]

    invalid_item_hits = 0
    gender_mismatch_hits = 0
    consistency_hits = 0

    for item in all_items:
        normalized = item.item_type.strip().lower()

        if normalized in forbidden:
            invalid_item_hits += 1

        if not style_tool.is_item_allowed_for_gender(item.item_type, gender):
            gender_mismatch_hits += 1

        if expected and normalized not in expected:
            consistency_hits += 1

    return CaseResult(
        name=case["name"],
        invalid_item_hits=invalid_item_hits,
        gender_mismatch_hits=gender_mismatch_hits,
        consistency_hits=consistency_hits,
        total_items=len(all_items),
    )


async def evaluate_cases(cases_path: Path) -> dict[str, Any]:
    raw = cases_path.read_text(encoding="utf-8")
    cases = json.loads(raw)

    results: list[CaseResult] = []
    for case in cases:
        results.append(await _run_case(case))

    total_items = sum(r.total_items for r in results)
    total_items = max(total_items, 1)

    invalid_hits = sum(r.invalid_item_hits for r in results)
    gender_hits = sum(r.gender_mismatch_hits for r in results)
    consistency_hits = sum(r.consistency_hits for r in results)

    return {
        "summary": {
            "num_cases": len(results),
            "total_items_evaluated": total_items,
            "invalid_item_rate": round(invalid_hits / total_items, 4),
            "gender_mismatch_rate": round(gender_hits / total_items, 4),
            "recommendation_consistency_error_rate": round(consistency_hits / total_items, 4),
        },
        "cases": [
            {
                "name": r.name,
                "invalid_item_hits": r.invalid_item_hits,
                "gender_mismatch_hits": r.gender_mismatch_hits,
                "consistency_hits": r.consistency_hits,
                "total_items": r.total_items,
            }
            for r in results
        ],
    }


async def main() -> None:
    base = Path(__file__).resolve().parent
    report = await evaluate_cases(base / "test_cases.json")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
