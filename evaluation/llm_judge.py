"""LLM-as-judge evaluation: explanation faithfulness and intent adherence.

The deterministic verifier already catches literal violations (garment types
not in the look). The judge adds semantic checks a regex can't:

- **faithfulness**: does the explanation claim colors, styles, or benefits
  the rule evidence doesn't support?
- **intent adherence**: does the outfit plausibly serve the stated occasion?

Calibration cases (hand-crafted good/bad pairs) run first — a judge that
can't separate them is reported as uncalibrated and its scores discarded.

Requires DEEPSEEK_API_KEY; costs a few paise per case. Run on demand::

    poetry run python evaluation/llm_judge.py --sample 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.base import AgentContext  # noqa: E402
from backend.agents.recommendation_agent import RecommendationAgent  # noqa: E402
from backend.agents.styling_agent import StylingAgent  # noqa: E402
from backend.schemas.clothing import ClothingAttributes, ClothingType, Color, Pattern, Style  # noqa: E402
from backend.services.llm import LLMService  # noqa: E402

_JUDGE_SYSTEM_PROMPT = (
    "You are an exacting evaluator of fashion-recommendation explanations. "
    "You receive the rule-engine EVIDENCE (the only permitted facts) and the EXPLANATION shown "
    "to the user. Judge whether every claim in the explanation is supported by the evidence. "
    "Style/tone words (e.g. 'clean', 'polished') are fine; unsupported items, colors, "
    "occasions, or fabric/benefit claims are violations. Be strict but not pedantic."
)

_ADHERENCE_SYSTEM_PROMPT = (
    "You are an exacting evaluator of outfit recommendations. Given a user's stated occasion "
    "and the recommended items, judge whether the outfit plausibly serves that occasion. "
    "Judge the items, not the wording."
)


class FaithfulnessVerdict(BaseModel):
    faithful: bool = Field(description="True when every explanation claim is supported by the evidence")
    violations: list[str] = Field(default_factory=list, description="Unsupported claims, verbatim quotes")


class AdherenceVerdict(BaseModel):
    adherent: bool = Field(description="True when the outfit plausibly serves the stated occasion")
    reasoning: str = Field(description="One-sentence justification")


# ── Calibration: the judge must separate these before its scores count ──

CALIBRATION_CASES = [
    {
        "name": "faithful_good",
        "evidence": [
            "Base garment: navy shirt (smart_casual)",
            "white trousers — white complements navy; paired via color rules",
        ],
        "explanation": "Your navy shirt pairs beautifully with white trousers — the white complements the navy.",
        "expected_faithful": True,
    },
    {
        "name": "unsupported_item_bad",
        "evidence": [
            "Base garment: navy shirt (smart_casual)",
            "white trousers — white complements navy; paired via color rules",
        ],
        "explanation": "Pair your navy shirt with white trousers and a red leather jacket for extra flair.",
        "expected_faithful": False,
    },
    {
        "name": "unsupported_benefit_bad",
        "evidence": [
            "Base garment: black jeans (streetwear)",
            "white t-shirt — white complements black; paired via color rules",
        ],
        "explanation": "The moisture-wicking white t-shirt keeps you cool and matches your black jeans.",
        "expected_faithful": False,
    },
]


async def judge_faithfulness(llm: LLMService, evidence: list[str], explanation: str) -> FaithfulnessVerdict:
    prompt = "EVIDENCE:\n" + "\n".join(f"- {fact}" for fact in evidence) + f"\n\nEXPLANATION:\n{explanation}"
    return await llm.structured(FaithfulnessVerdict, system_prompt=_JUDGE_SYSTEM_PROMPT, user_prompt=prompt)


async def judge_adherence(llm: LLMService, occasion: str, items: list[str]) -> AdherenceVerdict:
    prompt = f"Occasion: {occasion}\nRecommended items: {', '.join(items)}"
    return await llm.structured(AdherenceVerdict, system_prompt=_ADHERENCE_SYSTEM_PROMPT, user_prompt=prompt)


async def run_calibration(llm: LLMService) -> dict[str, Any]:
    correct = 0
    details = []
    for case in CALIBRATION_CASES:
        verdict = await judge_faithfulness(llm, case["evidence"], case["explanation"])
        ok = verdict.faithful == case["expected_faithful"]
        correct += ok
        details.append({"name": case["name"], "expected": case["expected_faithful"], "got": verdict.faithful})
    return {"passed": correct == len(CALIBRATION_CASES), "correct": correct, "details": details}


async def run_judged_eval(sample: int) -> dict[str, Any]:
    llm = LLMService()
    if not llm.enabled:
        raise SystemExit("DEEPSEEK_API_KEY required for LLM-as-judge evaluation")

    calibration = await run_calibration(llm)
    if not calibration["passed"]:
        return {"calibration": calibration, "error": "judge failed calibration; scores withheld"}

    cases = json.loads((Path(__file__).resolve().parent / "test_cases.json").read_text())
    sampled = [c for c in cases if c.get("kind") == "generated"][:: max(1, len(cases) // sample)][:sample]

    styling = StylingAgent()
    recommendation = RecommendationAgent(llm_service=llm)

    faithful = unfaithful = adherent = nonadherent = 0
    violations: list[dict[str, Any]] = []
    for case in sampled:
        i = case["input"]
        ctx = AgentContext(image_bytes=b"eval", gender=i["gender"], shopping_intent=i["gender"])
        ctx.clothing_attributes = ClothingAttributes(
            clothing_type=ClothingType(i["clothing_type"]),
            primary_color=Color(i["primary_color"]),
            pattern=Pattern(i.get("pattern", "solid")),
            style=Style(i["style"]),
            confidence=float(i.get("confidence", 0.8)),
        )
        ctx.metadata["intent"] = {"occasion": "office day"}
        ctx = await styling.run(ctx)
        ctx = await recommendation.run(ctx)

        for rec in ctx.recommendations[:1]:  # judge the primary look per case
            verdict = await judge_faithfulness(llm, rec.evidence, rec.overall_explanation)
            if verdict.faithful:
                faithful += 1
            else:
                unfaithful += 1
                violations.append({"case": case["name"], "violations": verdict.violations})

            items = [f"{item.color} {item.item_type}" for item in rec.items]
            adherence = await judge_adherence(llm, "office day", items)
            if adherence.adherent:
                adherent += 1
            else:
                nonadherent += 1

    judged = max(faithful + unfaithful, 1)
    return {
        "calibration": calibration,
        "summary": {
            "cases_judged": judged,
            "explanation_faithfulness_rate": round(faithful / judged, 4),
            "intent_adherence_rate": round(adherent / max(adherent + nonadherent, 1), 4),
        },
        "violations": violations,
    }


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="LLM-as-judge evaluation")
    parser.add_argument("--sample", type=int, default=8, help="number of eval cases to judge")
    args = parser.parse_args()

    report = await run_judged_eval(args.sample)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
