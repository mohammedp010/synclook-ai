"""Deterministic evaluation-case generator.

Produces the ``generated`` cases in ``test_cases.json`` by sweeping the
clothing-type × style grid while cycling colors, patterns, shopping intents,
and confidence levels. Structural metrics (empty recommendations, outfit
completeness, intent violations) need no hand-labeled expectations, so the
grid can be broad; hand-written *golden* cases carry ``expected`` item lists
and are the only input to the consistency metric.

Regenerate with::

    poetry run python evaluation/generate_cases.py

Golden cases (``"kind": "golden"``) in the existing file are preserved.
"""

from __future__ import annotations

import json
import sys
from itertools import cycle
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.clothing import ClothingType, Style  # noqa: E402
from backend.tools.style_rules import INVALID_ITEMS_BY_SHOPPING_INTENT  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "test_cases.json"

# Every wearable base type except OTHER (which is the low-confidence fallback).
_BASE_TYPES = [ct for ct in ClothingType if ct != ClothingType.OTHER]

_STYLES = [
    Style.FORMAL,
    Style.CASUAL,
    Style.SMART_CASUAL,
    Style.STREETWEAR,
    Style.SPORTY,
    Style.MINIMALIST,
]

_INTENTS = ["menswear", "womenswear", "unisex"]
_COLORS = ["black", "white", "navy", "blue", "grey", "beige", "olive", "brown", "red", "green"]
_PATTERNS = ["solid", "solid", "striped", "solid", "checkered", "solid"]
# Mix in genuinely low-confidence detections so the conservative-fallback
# path is exercised by the harness, not only by unit tests.
_CONFIDENCES = [0.85, 0.9, 0.35, 0.75]


def _forbidden_for_intent(intent: str) -> list[str]:
    """Intent policy violations — these are product policy, not derived from pairings."""
    return sorted(item.value for item in INVALID_ITEMS_BY_SHOPPING_INTENT.get(intent, set()))


def generate_cases() -> list[dict[str, Any]]:
    colors = cycle(_COLORS)
    patterns = cycle(_PATTERNS)
    intents = cycle(_INTENTS)
    confidences = cycle(_CONFIDENCES)

    cases: list[dict[str, Any]] = []
    for base_type in _BASE_TYPES:
        for style in _STYLES:
            intent = next(intents)
            # A menswear shopper uploading a womenswear-only garment is a
            # legal input; the *recommendations* still must respect intent.
            color = next(colors)
            pattern = next(patterns)
            confidence = next(confidences)
            cases.append(
                {
                    "name": f"{color}_{base_type.value}_{intent}_{style.value}",
                    "kind": "generated",
                    "input": {
                        "clothing_type": base_type.value,
                        "primary_color": color,
                        "pattern": pattern,
                        "style": style.value,
                        "confidence": confidence,
                        "gender": intent,
                    },
                    "forbidden": _forbidden_for_intent(intent),
                }
            )
    return cases


def main() -> None:
    existing: list[dict[str, Any]] = []
    if CASES_PATH.exists():
        existing = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    golden = [case for case in existing if case.get("kind", "golden") == "golden"]
    for case in golden:
        case["kind"] = "golden"

    cases = golden + generate_cases()
    CASES_PATH.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases ({len(golden)} golden, {len(cases) - len(golden)} generated) to {CASES_PATH}")


if __name__ == "__main__":
    main()
