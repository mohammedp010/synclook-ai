"""Upload guardrail — is this photo something we can style? (Phase 3)

Today a car, a crow or a logo gets a confident garment label and a full outfit
built around it. The guard stops that before styling, recommendation and the
paid shopping search run, with four outcomes rather than two (plan §3.2):

- ``pass`` — go ahead.
- ``degrade`` — go ahead, but tell the user something about the result (the
  subject is uncertain, or the photo shows several garments).
- ``retake`` — it is probably clothing, but the photo is unusable: too dark,
  too blurred, too small, or blank. Ask for a better photo.
- ``reject`` — not a clothing photo. Say so, kindly.

Each question goes to whatever answers it best:

- **Usability is code.** Blur, exposure and resolution are measurable pixel
  properties; asking a model would be the reference's §8.2 mistake. Re-blur
  residual for sharpness, mean CIE L* for exposure, L* spread for blank frames.
- **"Is this clothing?" is a judgment.** Jev judges the VLM's one-line account
  of what the photo shows. With no judgment the check is skipped (Phase 2's
  perception call reports ``is_clothing`` itself).

Thresholds live in ``core.guard_policy``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from backend.core import guard_policy as policy
from backend.core.exceptions import ImageProcessingError

FloatArray = NDArray[np.float64]

_GARMENT_PART = re.compile(
    r"\b(lining|collar|cuffs?|hem|trim|laces?|straps?|shoe trees?|charms?|buttons?|zippers?|pockets?|"
    r"soles?|fabric|towels?|brush(es)?|patch(es)?|logos?|labels?|tags?|hood|sleeves?|waistband)\b"
)

MULTI_GARMENT_MIN_OTHERS = 2
"""Separate items, beyond the main one, before the photo counts as an outfit.

The VLM lists everything visible, and the public labels count only what a photo
is *about*: on 102 single-garment photos it listed other items for 37. Most
were real (trousers under a shirt, heels with a dress); the errors were parts
and tags ("purple lining", "white price tag"). Filtering those in code: at ≥1
other item, recall 35/37 with 23/102 flagged; at ≥2, recall 27/37 with 10/102.
≥2 is used for the caveat — a note on a third of plain product shots would be
noise — and every separate item is still shown to the user either way."""


def separate_items(others: list[str]) -> list[str]:
    """The VLM's other visible items, minus parts of the main garment, tags and props.

    Tried in the prompt first ("never list collars, cuffs, lining…"). It made
    things worse: 37 → 42 flagged single-garment photos, and one real garment's
    guard score fell from 0.74 to 0.63. A filter in code is checkable; an
    instruction to a small model is not.
    """
    return [item for item in others if not _GARMENT_PART.search(item.lower())]


class GuardOutcome(str, Enum):
    PASS = "pass"
    DEGRADE = "degrade"
    RETAKE = "retake"
    REJECT = "reject"


@dataclass(frozen=True)
class QualityReport:
    min_side: int
    mean_lightness: float
    """Mean L* on 0-100."""
    lightness_spread: float
    """Std-dev of L*. Near zero is a blank frame."""
    sharpness: float
    """Mean change under a 1.5 px re-blur, over lightness contrast. Low is blurred."""
    problems: tuple[str, ...]


@dataclass(frozen=True)
class GuardDecision:
    outcome: GuardOutcome
    reason: str
    """Machine-readable: ``ok``, ``not_clothing``, ``too_dark``, ``multiple_garments``, …"""
    message: str
    """What to tell the user. Empty on ``pass``."""
    signals: dict[str, float | str | None] = field(default_factory=dict)


class UnusableImageError(ImageProcessingError):
    """The guard declined the upload. ``message`` is safe to show the user as is."""

    def __init__(self, decision: GuardDecision) -> None:
        super().__init__(decision.message, detail=decision.reason)
        self.decision = decision


# ── Usability (code) ─────────────────────────────────────────────────

_QUALITY_SIDE = 256
"""Measured at a fixed size so the numbers do not scale with resolution."""


def _lightness(grey: FloatArray) -> FloatArray:
    """8-bit sRGB grey → CIE L* (0-100). The real curve, not a gamma shortcut: a
    shortcut read a photo darkened to 6% brightness as L* 28 and let it through."""
    c = grey / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return np.asarray(np.where(lin > 0.008856, 116.0 * np.cbrt(lin) - 16.0, 903.3 * lin))


def quality_report(image: Image.Image) -> QualityReport:
    """Measure the photo. Deterministic and a few ms."""
    rgb = image.convert("RGB")
    min_side = min(rgb.size)

    grey = rgb.convert("L")
    grey.thumbnail((_QUALITY_SIDE, _QUALITY_SIDE), Image.Resampling.BILINEAR)
    g = np.asarray(grey, dtype=np.float64)
    lightness = _lightness(g)

    # Sharpness as "how much does a slight extra blur change it", relative to
    # contrast. A sharp photo loses edge detail to a 1.5 px blur; an already
    # blurred one barely changes. Raw Laplacian variance was tried first and
    # could not separate the two (real photos 87+, blurred copies up to 353),
    # because edge energy scales with scene contrast, not focus.
    reblurred = np.asarray(grey.filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float64)
    sharpness = float(np.abs(g - reblurred).mean() / max(float(g.std()), 1.0))

    mean_l = float(lightness.mean())
    spread = float(lightness.std())

    problems: list[str] = []
    if min_side < policy.MIN_SIDE_PX:
        problems.append("too_small")
    # Darkness first: an unlit photo also has almost no spread, and "too dark"
    # is the advice that fixes it, where "blank" would not.
    if mean_l < policy.MIN_MEAN_LIGHTNESS:
        problems.append("too_dark")
    elif spread < policy.MIN_LIGHTNESS_SPREAD:
        problems.append("blank")
    elif sharpness < policy.MIN_SHARPNESS:
        problems.append("blurred")

    return QualityReport(
        min_side=min_side,
        mean_lightness=round(mean_l, 2),
        lightness_spread=round(spread, 2),
        sharpness=round(sharpness, 4),
        problems=tuple(problems),
    )


_RETAKE_MESSAGES = {
    "too_small": "That image is very small. Could you upload a larger photo of the garment?",
    "blank": "That photo looks blank. Could you try again with the garment in frame?",
    "too_dark": "That photo is too dark to read the colours. Could you retake it in better light?",
    "blurred": "That photo is too blurry to read the details. Could you retake it holding the camera steady?",
}

_REJECT_MESSAGE = (
    "This doesn't look like a clothing photo{subject}. Upload a picture of a garment, "
    "shoes or an accessory and I'll style it."
)


def decide(
    quality: QualityReport,
    *,
    jev_garment_p: float | None = None,
    subject: str | None = None,
    garment_count: int = 1,
    main_item: str | None = None,
) -> GuardDecision:
    """Combine the signals into one of four outcomes. Policy numbers live in ``guard_policy``.

    A Jev reading decides "is this clothing": it judged the VLM's account of the
    photo. Usability is checked first — a blurred garment should be retaken,
    not rejected.
    """
    signals: dict[str, float | str | None] = {
        "jev_garment_p": None if jev_garment_p is None else round(jev_garment_p, 4),
        "sharpness": quality.sharpness,
        "mean_lightness": quality.mean_lightness,
        "subject": subject,
    }

    if quality.problems:
        reason = quality.problems[0]
        return GuardDecision(GuardOutcome.RETAKE, reason, _RETAKE_MESSAGES[reason], signals)

    if jev_garment_p is not None and jev_garment_p < policy.JEV_REJECT_BELOW:
        shown = f" (it looks like {subject})" if subject else ""
        return GuardDecision(GuardOutcome.REJECT, "not_clothing", _REJECT_MESSAGE.format(subject=shown), signals)
    if jev_garment_p is not None and jev_garment_p < policy.JEV_UNSURE_BELOW:
        return GuardDecision(
            GuardOutcome.DEGRADE,
            "uncertain_subject",
            "I'm not fully sure this is a garment, so treat these suggestions as a rough guide.",
            signals,
        )
    if garment_count > MULTI_GARMENT_MIN_OTHERS:
        main = f"the {main_item}" if main_item else "the main piece"
        return GuardDecision(
            GuardOutcome.DEGRADE,
            "multiple_garments",
            f"This photo shows a full outfit, so I've styled {main}.",
            signals,
        )
    return GuardDecision(GuardOutcome.PASS, "ok", "", signals)
