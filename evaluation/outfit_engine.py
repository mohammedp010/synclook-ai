"""Outfit-engine eval: demo closet variants × 14 occasions × weather, no model calls.

Reports, per closet variant and overall:

- ``empty_rate``: requests that returned no outfit;
- ``full_rate``: requests that returned all 3 outfits;
- ``violations``: rule breaks found by ``engine.outfits.violations`` on every returned
  outfit, plus repeated items and items not in the closet. **Must be 0**;
- ``ms_mean`` / ``ms_p95``: engine time per request (milliseconds; no network or DB).

The closet variants are fixed subsets of the demo closet, so a change to the
rules shows up as a change in these numbers rather than in one hand-picked case.

Usage::

    poetry run python evaluation/outfit_engine.py            # print the report
    poetry run python evaluation/outfit_engine.py --check    # exit 1 on a regression (CI)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from statistics import mean, quantiles
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.outfits import MAX_OUTFITS, ClosetItem, Weather, build_outfits, violations  # noqa: E402
from backend.schemas.taxonomy import GarmentCategory, Occasion  # noqa: E402
from backend.services.closet import demo_items  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "outfit_engine_baseline.json"

WEATHERS: dict[str, Weather | None] = {
    "none": None,
    "cold_rain": Weather(temperature_c=6, rain=True),
    "mild": Weather(temperature_c=20, rain=False),
    "hot": Weather(temperature_c=32, rain=False),
}

# Gates for --check. Empty and full rates are floors/ceilings on the full demo closet,
# set from the first run (2026-11-15) with a little room; violations are never allowed.
THRESHOLDS = {
    "full_closet_empty_rate_max": 0.10,
    "full_closet_full_rate_min": 0.80,
    "violations_max": 0,
    "ms_p95_max": 250.0,
}


def demo_closet() -> list[ClosetItem]:
    return [ClosetItem(id=f"demo-{n:02d}", **tags.model_dump()) for n, (tags, _) in enumerate(demo_items(), 1)]


def variants(full: list[ClosetItem]) -> dict[str, list[ClosetItem]]:
    rng = random.Random(7)
    return {
        "full": full,
        "half": sorted(rng.sample(full, len(full) // 2), key=lambda i: i.id),
        "no_footwear": [i for i in full if i.category != GarmentCategory.FOOTWEAR],
        "no_outerwear": [i for i in full if i.category != GarmentCategory.OUTERWEAR],
        "no_accessories": [i for i in full if i.category != GarmentCategory.ACCESSORY],
    }


def run() -> dict[str, Any]:
    report: dict[str, Any] = {"variants": {}, "violations": [], "per_occasion_full_closet": {}}
    all_ms: list[float] = []
    for name, closet in variants(demo_closet()).items():
        ids = {i.id for i in closet}
        counts: list[int] = []
        for weather_name, weather in WEATHERS.items():
            for occasion in Occasion:
                start = time.perf_counter()
                result = build_outfits(closet, occasion, weather)
                all_ms.append((time.perf_counter() - start) * 1000)
                counts.append(len(result.outfits))
                if name == "full":
                    report["per_occasion_full_closet"].setdefault(occasion.value, {})[weather_name] = len(
                        result.outfits
                    )
                for outfit in result.outfits:
                    found = violations(outfit, occasion, weather)
                    if not set(outfit.item_ids) <= ids:
                        found.append("an item is not in this closet")
                    for problem in found:
                        report["violations"].append(
                            {"variant": name, "weather": weather_name, "occasion": occasion.value, "problem": problem}
                        )
                if not result.outfits and not result.reason:
                    report["violations"].append(
                        {"variant": name, "weather": weather_name, "occasion": occasion.value, "problem": "no reason"}
                    )
        report["variants"][name] = {
            "items": len(closet),
            "requests": len(counts),
            "empty_rate": round(sum(c == 0 for c in counts) / len(counts), 3),
            "full_rate": round(sum(c == MAX_OUTFITS for c in counts) / len(counts), 3),
        }
    report["summary"] = {
        "requests": len(all_ms),
        "violations": len(report["violations"]),
        "ms_mean": round(mean(all_ms), 2),
        "ms_p95": round(quantiles(all_ms, n=20)[-1], 2),
    }
    return report


def check(report: dict[str, Any]) -> list[str]:
    full = report["variants"]["full"]
    summary = report["summary"]
    failures = []
    if full["empty_rate"] > THRESHOLDS["full_closet_empty_rate_max"]:
        failures.append(f"full-closet empty rate {full['empty_rate']} > {THRESHOLDS['full_closet_empty_rate_max']}")
    if full["full_rate"] < THRESHOLDS["full_closet_full_rate_min"]:
        failures.append(f"full-closet 3-outfit rate {full['full_rate']} < {THRESHOLDS['full_closet_full_rate_min']}")
    if summary["violations"] > THRESHOLDS["violations_max"]:
        failures.append(f"{summary['violations']} rule violations: {report['violations'][:3]}")
    if summary["ms_p95"] > THRESHOLDS["ms_p95_max"]:
        failures.append(f"p95 {summary['ms_p95']} ms > {THRESHOLDS['ms_p95_max']} ms")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when a threshold is broken")
    parser.add_argument("--write", action="store_true", help=f"save the report to {BASELINE.name}")
    args = parser.parse_args()

    report = run()
    print(json.dumps({"variants": report["variants"], "summary": report["summary"]}, indent=2))
    if args.write:
        BASELINE.write_text(json.dumps(report, indent=2) + "\n")
    if args.check:
        failures = check(report)
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
