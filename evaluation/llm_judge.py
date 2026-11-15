"""LLM-as-judge evaluation of ``POST /outfits``: explanation faithfulness and occasion fit.

The local check in ``services.outfit_explainer`` already rejects explanations that
name a garment the outfit lacks. The judge adds what a word list cannot:

- **faithfulness**: does the explanation claim colours, occasions or benefits the
  rule evidence does not support?
- **adherence**: do the outfit's items plausibly serve the occasion?

Cases: the demo closet × every ``Occasion`` (no weather) → the engine's outfits →
the production explainer (the app's text model) → the judge. The judge is a
**different model** (``--judge-model``, default ``openai/gpt-4o-mini``) so the
writer does not grade itself. Calibration cases run first; a judge that cannot
separate them is reported as uncalibrated and its scores withheld.

Every model reply is cached on disk (``evaluation/.cache/llm_judge/``), so a re-run
costs nothing. First run: about 14 explainer + 87 judge calls, roughly $0.02::

    poetry run python evaluation/llm_judge.py
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import Settings, get_settings  # noqa: E402
from backend.engine.outfits import build_outfits  # noqa: E402
from backend.schemas.taxonomy import Occasion  # noqa: E402
from backend.services.llm import LLMService  # noqa: E402
from backend.services.outfit_explainer import PROMPT_VERSION, explain, unowned_garments  # noqa: E402
from evaluation.outfit_engine import demo_closet  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "llm_judge"
REPORT = Path(__file__).resolve().parent / "llm_judge_outfits.json"
DEFAULT_JUDGE = "openai/gpt-4o-mini"


class CachedLLM(LLMService):
    """``structured`` replies cached on disk by model, schema and prompts."""

    calls = 0

    async def structured[T: BaseModel](self, schema: type[T], *, system_prompt: str, user_prompt: str) -> T:
        model = self._settings.text_model
        key = hashlib.sha256("\x00".join((model, schema.__name__, system_prompt, user_prompt)).encode()).hexdigest()
        path = CACHE_DIR / f"{key}.json"
        if path.exists():
            return schema.model_validate_json(path.read_text())
        CachedLLM.calls += 1
        result = await super().structured(schema, system_prompt=system_prompt, user_prompt=user_prompt)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json())
        return result


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


class CalibrationCase(NamedTuple):
    """A hand-labelled faithfulness example with the verdict the judge must reach."""

    name: str
    evidence: list[str]
    explanation: str
    expected_faithful: bool


CALIBRATION_CASES = [
    CalibrationCase(
        name="faithful_good",
        evidence=[
            "Base garment: navy shirt (smart_casual)",
            "white trousers — white complements navy; paired via color rules",
        ],
        explanation="Your navy shirt pairs beautifully with white trousers — the white complements the navy.",
        expected_faithful=True,
    ),
    CalibrationCase(
        name="unsupported_item_bad",
        evidence=[
            "Base garment: navy shirt (smart_casual)",
            "white trousers — white complements navy; paired via color rules",
        ],
        explanation="Pair your navy shirt with white trousers and a red leather jacket for extra flair.",
        expected_faithful=False,
    ),
    CalibrationCase(
        name="unsupported_benefit_bad",
        evidence=[
            "Base garment: black jeans (streetwear)",
            "white t-shirt — white complements black; paired via color rules",
        ],
        explanation="The moisture-wicking white t-shirt keeps you cool and matches your black jeans.",
        expected_faithful=False,
    ),
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
        verdict = await judge_faithfulness(llm, case.evidence, case.explanation)
        ok = verdict.faithful == case.expected_faithful
        correct += ok
        details.append({"name": case.name, "expected": case.expected_faithful, "got": verdict.faithful})
    return {"passed": correct == len(CALIBRATION_CASES), "correct": correct, "details": details}


async def run_judged_eval(judge_model: str) -> dict[str, Any]:
    settings: Settings = get_settings()
    if not settings.vlm_api_key:
        raise SystemExit("VLM_API_KEY (OpenRouter) required for LLM-as-judge evaluation")
    if judge_model == settings.text_model:
        raise SystemExit("the judge must not be the model that writes the explanations")
    writer = CachedLLM(settings)
    judge = CachedLLM(settings.model_copy(update={"text_model": judge_model}))

    calibration = await run_calibration(judge)
    if not calibration["passed"]:
        return {"calibration": calibration, "error": "judge failed calibration; scores withheld"}

    closet = demo_closet()
    faithful = adherent = judged = from_model = 0
    violations: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    for occasion in Occasion:
        outfits = build_outfits(closet, occasion).outfits
        for outfit, explanation in zip(outfits, await explain(writer, outfits, occasion), strict=True):
            judged += 1
            from_model += explanation.source == "model"
            assert not unowned_garments(explanation.text, outfit)  # the local check held
            verdict = await judge_faithfulness(judge, list(outfit.evidence), explanation.text)
            faithful += verdict.faithful
            if not verdict.faithful:
                violations.append({"occasion": occasion.value, "text": explanation.text, "why": verdict.violations})
            items = [i.short_label for i in outfit.items]
            adherence = await judge_adherence(judge, occasion.value.replace("_", " "), items)
            adherent += adherence.adherent
            if not adherence.adherent:
                misses.append({"occasion": occasion.value, "items": items, "reasoning": adherence.reasoning})

    return {
        "writer_model": settings.text_model,
        "judge_model": judge_model,
        "prompt_version": PROMPT_VERSION,
        "calibration": calibration,
        "summary": {
            "outfits_judged": judged,
            "model_written_rate": round(from_model / max(judged, 1), 4),
            "explanation_faithfulness_rate": round(faithful / max(judged, 1), 4),
            "occasion_adherence_rate": round(adherent / max(judged, 1), 4),
            "paid_calls_this_run": CachedLLM.calls,
        },
        "violations": violations,
        "adherence_misses": misses,
    }


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="LLM-as-judge evaluation of POST /outfits")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE, help="OpenRouter model id; not the writer model")
    args = parser.parse_args()

    report = await run_judged_eval(args.judge_model)
    print(json.dumps(report, indent=2))
    if report.get("summary") is None:
        print("warning: judge failed calibration; no summary", file=sys.stderr)
    else:
        REPORT.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
