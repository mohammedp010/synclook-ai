"""Perception eval — what production perception gets right on the ``public`` split.

Production (``services.perception``) describes the photo with the vision model,
has Jev judge the description, then fills colour shade, category, pattern and
item count in code. This scores that exact path (``description_from`` +
``tags_from``) on 191 labelled photos: 139 garment photos, 52 that are not.

How it was chosen: ``perception_arms_public.json`` records the 2026-11-15 run
against one structured vision call (arm A). Rule fixed before the run: ship A
unless this path beats it by 3 points on garment type or formality. It won
formality 0.727 vs 0.676; A won occasions (F1 0.67 vs 0.51) and pattern. A's
code was then deleted; its cached replies remain on disk.

The labels were written inside this project from studio and museum photos: a
regression check, not proof of real-world accuracy.

Every reply is cached on disk (``data/perception/.vlm_cache``, ``.judge_cache``),
so a re-run, or a re-score after a scoring change, costs nothing::

    poetry run python evaluation/perception.py
    poetry run python evaluation/perception.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.schemas.taxonomy import (  # noqa: E402
    COARSE_COLOR,
    COARSE_PATTERN,
    COARSE_TYPE,
    ColorName,
    GarmentType,
    PatternName,
)
from backend.services.garment_description import PROMPT_VERSION as DESCRIBE_VERSION  # noqa: E402
from backend.services.garment_description import GarmentDescriber, VisualDescription, VLMUnavailableError  # noqa: E402
from backend.services.garment_judge import (  # noqa: E402
    QUESTIONS_VERSION,
    GarmentDescription,
    GarmentJudge,
    GarmentJudgment,
    description_from,
)
from backend.services.image_guard import UnusableImageError  # noqa: E402
from backend.services.jev import JevError  # noqa: E402
from backend.services.perception import category_of, measured_colour, tags_from  # noqa: E402
from evaluation.perception_labels import IMAGES_DIR, PerceptionLabel, load_labels  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data" / "perception"
VLM_CACHE_DIR = DATA_DIR / ".vlm_cache"
JUDGE_CACHE_DIR = DATA_DIR / ".judge_cache"


def _slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def _key(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:24]


async def describe_cached(describer: GarmentDescriber, image_bytes: bytes) -> VisualDescription:
    """``GarmentDescriber.describe`` behind the on-disk cache (the old eval's layout, so old replies are reused)."""
    path = VLM_CACHE_DIR / _slug(describer.model) / DESCRIBE_VERSION / f"{_key(image_bytes)}.json"
    if path.is_file():
        return VisualDescription(**json.loads(path.read_text(encoding="utf-8")))
    description = await describer.describe(image_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(description), indent=1), encoding="utf-8")
    return description


async def judge_cached(judge: GarmentJudge, description: GarmentDescription) -> GarmentJudgment:
    state = json.dumps(description.to_state(), sort_keys=True)
    path = JUDGE_CACHE_DIR / get_settings().jev_model / QUESTIONS_VERSION / f"{_key(state.encode())}.json"
    if path.is_file():
        return GarmentJudgment.from_json(json.loads(path.read_text(encoding="utf-8")))
    judgment = await judge.judge(description)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(judgment.to_json(), indent=1), encoding="utf-8")
    return judgment


async def predict(
    describer: GarmentDescriber, judge: GarmentJudge, image_bytes: bytes, image: Image.Image
) -> dict[str, Any]:
    """Production's two calls (cached on disk) and production's code steps."""
    vlm = await describe_cached(describer, image_bytes)
    judgment = await judge_cached(judge, description_from(vlm, measured_colour(vlm, image).name.value))
    out: dict[str, Any] = {"cost_usd": vlm.cost_usd, "latency_ms": vlm.latency_ms + judgment.latency_ms}
    try:
        tags = tags_from(vlm, judgment, image)
    except UnusableImageError:
        return out | {"rejected": True}
    return out | {
        "rejected": False,
        "garment_type": tags.garment_type,
        "color": tags.color.value,
        "pattern": tags.pattern.value,
        "formality": int(tags.formality),
        "occasions": [o.value for o in tags.occasions],
        "warmth": tags.warmth.value,
    }


# ── Scoring ──────────────────────────────────────────────────────────


def _truth_type(label: PerceptionLabel) -> str:
    assert label.primary is not None
    return label.primary.accessory.value if label.primary.accessory is not None else label.primary.type.value


def _coarse_type(value: str) -> str:
    member = GarmentType._value2member_map_.get(value)
    if isinstance(member, GarmentType):
        return COARSE_TYPE.get(member, "other")
    return "accessory" if category_of(value).value == "accessory" else "other"


def score(label: PerceptionLabel, pred: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"image": label.image, "garment_photo": label.is_garment_photo, "rejected": pred["rejected"]}
    if not label.is_garment_photo or label.primary is None or pred["rejected"]:
        return row
    truth_type, truth = _truth_type(label), label.primary
    got_colour, want_colour = ColorName(pred["color"]), truth.primary_color
    got_occ, want_occ = set(pred["occasions"]), {o.value for o in label.occasions}
    return row | {
        "type_fine": pred["garment_type"] == truth_type,
        "type_coarse": _coarse_type(pred["garment_type"]) == _coarse_type(truth_type),
        "type_category": category_of(pred["garment_type"]) == category_of(truth_type),
        "color_fine": got_colour == want_colour,
        "color_coarse": COARSE_COLOR[got_colour] == COARSE_COLOR[want_colour],
        "pattern_fine": pred["pattern"] == truth.pattern.value,
        "pattern_coarse": COARSE_PATTERN.get(PatternName(pred["pattern"])) == COARSE_PATTERN.get(truth.pattern),
        "formality_exact": pred["formality"] == int(label.formality),
        "formality_abs_err": abs(pred["formality"] - int(label.formality)),
        "occ_tp": len(got_occ & want_occ),
        "occ_fp": len(got_occ - want_occ),
        "occ_fn": len(want_occ - got_occ),
        "got_type": pred["garment_type"],
        "want_type": truth_type,
    }


def aggregate(rows: list[dict[str, Any]], preds: list[dict[str, Any]]) -> dict[str, Any]:
    garments = [r for r in rows if r["garment_photo"]]
    scored = [r for r in garments if not r["rejected"]]
    others = [r for r in rows if not r["garment_photo"]]

    def rate(key: str) -> float:
        # Over every garment photo: a false rejection counts as a miss, not as excused.
        return round(sum(bool(r.get(key)) for r in garments) / max(len(garments), 1), 4)

    tp, fp, fn = (sum(r.get(k, 0) for r in scored) for k in ("occ_tp", "occ_fp", "occ_fn"))
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {
        "n_photos": len(rows),
        "n_garment_photos": len(garments),
        "false_rejects": sum(r["rejected"] for r in garments),
        "non_garments_caught": round(sum(r["rejected"] for r in others) / max(len(others), 1), 4),
        "type_fine": rate("type_fine"),
        "type_coarse": rate("type_coarse"),
        "type_category": rate("type_category"),
        "color_fine": rate("color_fine"),
        "color_coarse": rate("color_coarse"),
        "pattern_fine": rate("pattern_fine"),
        "pattern_coarse": rate("pattern_coarse"),
        "formality_exact": rate("formality_exact"),
        "formality_mae": round(mean(r["formality_abs_err"] for r in scored), 4) if scored else None,
        "occasion_precision": round(precision, 4),
        "occasion_recall": round(recall, 4),
        "occasion_f1": round(2 * precision * recall / max(precision + recall, 1e-9), 4),
        "cost_per_1000_usd": round(1000 * mean(p["cost_usd"] for p in preds), 4) if preds else None,
        "median_latency_ms": round(median(p["latency_ms"] for p in preds)) if preds else None,
    }


# ── Run ──────────────────────────────────────────────────────────────


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="Production perception on the public split")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    labels = sorted((lb for lb in load_labels().values() if lb.split == "public"), key=lambda lb: lb.image)
    labels = labels[: args.limit] if args.limit else labels
    describer, judge = GarmentDescriber(), GarmentJudge()
    gate = asyncio.Semaphore(args.concurrency)
    errors: list[dict[str, str]] = []

    async def one(label: PerceptionLabel) -> dict[str, Any] | None:
        image = Image.open(IMAGES_DIR / label.image)
        image.load()
        async with gate:
            try:
                return await predict(describer, judge, (IMAGES_DIR / label.image).read_bytes(), image)
            except (VLMUnavailableError, JevError) as exc:
                errors.append({"image": label.image, "error": str(exc)})
                return None

    results = await asyncio.gather(*(one(lb) for lb in labels))
    await judge.aclose()
    pairs = [(lb, p) for lb, p in zip(labels, results) if p is not None]
    rows = [score(lb, p) for lb, p in pairs]
    report = {
        "split": "public",
        "vision_model": describer.model,
        "metrics": aggregate(rows, [p for _, p in pairs]),
        "warmth": dict(Counter(p["warmth"] for _, p in pairs if not p["rejected"])),
        "errors": errors,
        "type_misses": [
            f"{r['want_type']} -> {r['got_type']}" for r in rows if "type_fine" in r and not r["type_fine"]
        ],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
