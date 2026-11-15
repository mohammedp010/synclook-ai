"""Occasion-intent eval — does the request parser type the occasion right?

The parser (``LLMService.extract_intent``) fills ``StyleIntent.occasion_type``
in the same call as budget and avoid-list. It replaced a separate Jev choice
over the taxonomy, which scored 0.984 on these 64 requests; a dedicated
occasion-only LLM call scored the same (``occasion_intent_eval.json`` keeps
that earlier run). This eval checks the merged call did not lose that.

Cases (``occasion_intent_cases.json``): four per occasion plus eight that name
none. A prediction is correct when it is the label or one of the case's
``also`` alternatives (a sangeet is a wedding *and* festive); a ``null`` label
is correct only when the parser says no occasion. The labels are model-written,
so read the number as a regression check, not an accuracy to quote.

Replies are cached on disk (``evaluation/.cache/``), so a re-run is free::

    poetry run python evaluation/occasion_intent.py           # ~64 text calls, < $0.01 cold
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.schemas.intent import StyleIntent  # noqa: E402
from backend.services.llm import _INTENT_SYSTEM_PROMPT, LLMService  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "occasion_intent_cases.json"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "occasion_intent"


def correct(predicted: str | None, case: dict[str, Any]) -> bool:
    if case["occasion"] is None:
        return predicted is None
    return predicted == case["occasion"] or predicted in case["also"]


async def parse_cached(llm: LLMService, text: str) -> StyleIntent:
    model = get_settings().text_model
    key = hashlib.sha256(f"{model}\n{_INTENT_SYSTEM_PROMPT}\n{text}".encode()).hexdigest()[:24]
    path = CACHE_DIR / model.replace("/", "__") / f"{key}.json"
    if path.is_file():
        return StyleIntent.model_validate_json(path.read_text(encoding="utf-8"))
    intent = await llm.extract_intent(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(intent.model_dump_json(), encoding="utf-8")
    return intent


async def run() -> dict[str, Any]:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text())
    llm = LLMService()
    if not llm.enabled:
        raise SystemExit("VLM_API_KEY (OpenRouter) is required")
    rows = []
    for case in cases:
        intent = await parse_cached(llm, case["text"])
        got = intent.occasion_type.value if intent.occasion_type else None
        rows.append({"text": case["text"], "label": case["occasion"], "got": got, "ok": correct(got, case)})

    named = [r for r in rows if r["label"] is not None]
    return {
        "model": get_settings().text_model,
        "n": len(rows),
        "accuracy": round(sum(r["ok"] for r in rows) / len(rows), 4),
        "accuracy_named": round(sum(r["ok"] for r in named) / len(named), 4),
        "false_occasion_on_none": sum(r["got"] is not None for r in rows if r["label"] is None),
        "missed_named": sum(r["got"] is None for r in named),
        "errors": [r for r in rows if not r["ok"]],
    }


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    argparse.ArgumentParser(description="Request parser: is the occasion typed right?").parse_args()
    print(json.dumps(await run(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
