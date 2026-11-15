"""Occasion thresholds — where a Jev probability becomes a decision.

Kept apart from the questions on purpose. The Jev reference's governing rule is
*questions describe judgments; code owns thresholds*, and its §6.1 is blunt
that thresholds are domain- and version-specific: copy none from the docs,
calibrate on your own labels, recalibrate when the model changes. So every
number here is tied to the model it was set against, and changing one is a
reviewable diff rather than a prompt edit.

Two rules from the reference that this module exists to respect:

- **Noul thresholds are never reused for a choice** (§8.8). These are noul
  thresholds and are only read by code that asks occasion nouls.
- **Occasion is multi-label.** A navy blazer can clear the bar for business,
  smart-casual and a wedding at once; that is the right answer, not indecision.
"""

from __future__ import annotations

from backend.schemas.taxonomy import Occasion

CALIBRATED_FOR = "jev-1.13.0"
"""The model these thresholds were set against. ``garment_judge`` logs a warning
when Jev answers as anything else — the numbers below may then be wrong."""

OCCASION_THRESHOLD = 0.5
"""Default bar for "this garment suits this occasion".

0.5 is the noul's own midpoint, not a fitted value — chosen before looking at
results so the public-split number is not tuned to its labels. The eval prints
F1 across a threshold sweep; move this only on ``holdout`` evidence."""

OCCASION_THRESHOLD_OVERRIDES: dict[Occasion, float] = {}
"""Per-occasion bars, for when calibration shows one occasion runs hot or cold.
Empty until holdout labels exist to justify an entry."""


def threshold_for(occasion: Occasion) -> float:
    return OCCASION_THRESHOLD_OVERRIDES.get(occasion, OCCASION_THRESHOLD)


def occasions_from(probabilities: dict[Occasion, float]) -> list[Occasion]:
    """Occasions that clear their bar, most probable first."""
    kept = [occ for occ, p in probabilities.items() if p >= threshold_for(occ)]
    return sorted(kept, key=lambda occ: probabilities[occ], reverse=True)
