"""Garment judgments from Jev — occasion fit, formality, aesthetic (plan L3).

The perception cascade splits *seeing* from *judging*. Something that can see
(CLIP and the colour extractor today; a VLM once one is configured) turns the
photo into a short text description, and Jev judges that description. This
module is the judging half. It takes text in, so it does not care which seer
wrote it — adding the VLM later changes ``GarmentDescription``, not this file's
questions.

One batched call per garment (speculative fan-out, reference §7.2):

- 14 occasion **nouls** — one per occasion, because occasion fit is not
  mutually exclusive. A ``choice`` would force the occasions to compete for one
  unit of probability, which is the wrong question (reference §3.3, §8.8).
- 1 formality **score** over ``FORMALITY_CRITERIA`` — an ordered ladder, so a
  score, with levels written as situations rather than degrees.
- 1 aesthetic **choice** — one visual register per garment, with an ``other``
  escape.
- 1 garment-type **choice** over the full taxonomy — extraction from whatever
  words the seer used.

Questions only. Thresholds live in ``core.occasion_policy``; whether an outage
fails open or closed is the caller's decision (``JevUnavailableError``
propagates).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from backend.core.logging import get_logger
from backend.core.occasion_policy import CALIBRATED_FOR, occasions_from
from backend.schemas.perception import Warmth
from backend.schemas.taxonomy import (
    FORMALITY_CRITERIA,
    GARMENT_TYPE_OPTIONS,
    OCCASION_DESCRIPTIONS,
    Aesthetic,
    Formality,
    Occasion,
)
from backend.services.garment_description import VisualDescription
from backend.services.jev import Choice, JevClient, Noul, Question, Score

logger = get_logger(__name__)


AESTHETIC_DESCRIPTIONS: dict[Aesthetic, str | None] = {
    Aesthetic.MINIMALIST: "plain, clean lines, muted colours, no visible branding or ornament",
    Aesthetic.CLASSIC: "timeless tailored staples — oxford shirts, trench coats, loafers",
    Aesthetic.STREETWEAR: "urban youth style — graphic tees, hoodies, sneakers, oversized fits",
    Aesthetic.SPORTY: "athletic or performance wear, worn for sport or styled like it",
    Aesthetic.BOHEMIAN: "loose, flowing, earthy, folk prints and natural textures",
    Aesthetic.PREPPY: "polished collegiate style — polos, chinos, cable knits, blazers with crests",
    Aesthetic.EDGY: "dark, rebellious — leather, studs, distressed denim, heavy boots",
    Aesthetic.ROMANTIC: "soft and feminine — ruffles, lace, florals, pastels",
    Aesthetic.ETHNIC_TRADITIONAL: "traditional or regional dress — kurtas, sarees, sherwanis, lehengas",
    Aesthetic.OTHER: None,
}


@dataclass(frozen=True)
class GarmentDescription:
    """What the seeing layer knows, as words. Jev is text-only (reference §5.5)."""

    garment: str
    """e.g. ``"blazer"``, ``"kurta"`` — the most specific type available."""
    colour: str | None = None
    secondary_colour: str | None = None
    pattern: str | None = None
    fabric: str | None = None
    fit: str | None = None
    detail: str | None = None
    """Free-text description from a VLM, when one is configured."""
    other_garments: tuple[str, ...] = ()
    photo_subject: str | None = None
    """The VLM's account of what the photo shows — clothing or not. Guard input."""
    photo_setting: str | None = None

    def to_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {"garment": self.garment}
        if self.colour:
            state["colour"] = self.colour.replace("_", " ")
        if self.secondary_colour:
            state["secondary_colour"] = self.secondary_colour.replace("_", " ")
        if self.pattern and self.pattern not in {"solid", "other"}:
            state["pattern"] = self.pattern.replace("_", " ")
        if self.fabric:
            state["fabric"] = self.fabric
        if self.fit:
            state["fit"] = self.fit
        if self.detail:
            state["detail"] = self.detail
        if self.other_garments:
            state["also_visible"] = list(self.other_garments)
        if self.photo_subject:
            state["photo_shows"] = self.photo_subject
        if self.photo_setting:
            state["photo_setting"] = self.photo_setting
        return state


def description_from(vlm: VisualDescription, colour: str | None) -> GarmentDescription:
    """The one place a photo description becomes Jev's ``state``.

    Production (``services.perception``) and the perception eval both call it,
    so the eval measures exactly what production sends. ``colour`` is the
    measured colour name (the VLM's word picks the family, the pixels the shade).
    """
    if not vlm.item:
        # The VLM looked and named no garment. A state reading "garment: jacket
        # … photo_shows: a brick wall" once made Jev call the brick wall clothing
        # at 0.97 (reference §8.5, distractors in state), so the photo's own
        # account stands alone.
        return GarmentDescription(garment="none identified", photo_subject=vlm.subject, photo_setting=vlm.setting)
    return GarmentDescription(
        garment=vlm.item,
        colour=colour,
        pattern=vlm.pattern,
        fabric=vlm.fabric,
        fit=vlm.fit,
        detail=vlm.details,
        other_garments=tuple(vlm.other_garments[:4]),
        photo_subject=vlm.subject,
        photo_setting=vlm.setting,
    )


@dataclass(frozen=True)
class GarmentJudgment:
    occasion_p: dict[Occasion, float]
    occasions: list[Occasion]
    """Those clearing ``occasion_policy``, most probable first."""
    formality: Formality
    formality_score: float
    formality_confidence: float
    aesthetic: Aesthetic
    aesthetic_confidence: float
    garment_type: str
    """A GarmentType or AccessoryType value, or "other" — Jev's reading of the description."""
    garment_type_confidence: float
    garment_type_probabilities: dict[str, float]
    garment_photo_p: float
    """Upload guard: is the photo mainly about clothing? Reads the VLM's ``photo_subject``."""
    warmth: Warmth
    model: str
    latency_ms: float

    def to_json(self) -> dict[str, Any]:
        """Plain JSON for the kv_cache and the eval's disk cache."""
        data = asdict(self)
        data["occasion_p"] = {occ.value: p for occ, p in self.occasion_p.items()}
        data["occasions"] = [occ.value for occ in self.occasions]
        data["formality"] = int(self.formality)
        data["aesthetic"] = self.aesthetic.value
        data["warmth"] = self.warmth.value
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> GarmentJudgment:
        typed: dict[str, Any] = {
            "occasion_p": {Occasion(k): p for k, p in data["occasion_p"].items()},
            "occasions": [Occasion(o) for o in data["occasions"]],
            "formality": Formality(data["formality"]),
            "aesthetic": Aesthetic(data["aesthetic"]),
            "warmth": Warmth(data["warmth"]),
        }
        return cls(**(data | typed))


def _occasion_key(occ: Occasion) -> str:
    return f"occ_{occ.value}"


def build_questions() -> dict[str, Question]:
    questions: dict[str, Question] = {
        _occasion_key(occ): Noul(
            f"Would a well-dressed person wear the garment in `garment` for {desc}?",
            true="It suits this occasion, worn as part of an appropriate outfit",
            false="It would look out of place at this occasion",
        )
        for occ, desc in OCCASION_DESCRIPTIONS.items()
    }
    questions["formality"] = Score("How formal is the garment in `garment`?", tuple(FORMALITY_CRITERIA))
    # Extraction as a bounded choice (reference §8.9): the VLM writes "anarkali
    # kurta" in free text, and Jev maps it onto the taxonomy. 80 options is well
    # inside the 255 limit and costs a few tokens each. Names carry the signal,
    # so descriptions are null.
    questions["garment_type"] = Choice(
        "Which item is the garment described in `garment`?",
        {name: None for name in GARMENT_TYPE_OPTIONS},
    )
    # Upload guard, asked in the same call (speculative fan-out: free). Reads the
    # VLM's description of the photo, not the garment fields, which a VLM fills
    # with its best guess even for a photo of a car.
    questions["garment_photo"] = Noul(
        "Is the photo described in `photo_shows` mainly about clothing, footwear or a fashion accessory — "
        "a garment shown on its own, or a person photographed to show what they are wearing?",
        true="The photo is about clothing someone could ask how to style",
        false="Clothing is absent or incidental — the photo is about something else",
    )
    questions["aesthetic"] = Choice(
        "Which visual style does the garment in `garment` belong to?",
        {a.value: desc for a, desc in AESTHETIC_DESCRIPTIONS.items()},
    )
    # Warmth is judged from the words (fabric, padding, sleeves), like formality.
    questions["warmth"] = Choice(
        "How warm is the garment in `garment` to wear?",
        {
            Warmth.LIGHT.value: "Light — summer weight: thin cotton or linen, short sleeves, sandals, most accessories",
            Warmth.MEDIUM.value: "Medium — for mild weather: jeans, long-sleeve shirts, light knits, sneakers",
            Warmth.HEAVY.value: "Heavy — for cold weather: wool coats, padded or puffer jackets, thick knits, boots",
        },
    )
    return questions


_QUESTIONS = build_questions()
QUESTIONS_VERSION = hashlib.sha256(
    json.dumps({k: q.to_json() for k, q in _QUESTIONS.items()}, sort_keys=True).encode()
).hexdigest()[:8]
"""Part of every cached judgment's key, so a changed question never serves an old answer."""


class GarmentJudge:
    def __init__(self, client: JevClient | None = None) -> None:
        self._client = client or JevClient()

    @property
    def enabled(self) -> bool:
        return self._client.enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def judge(self, description: GarmentDescription) -> GarmentJudgment:
        resp = await self._client.judge(description.to_state(), _QUESTIONS)
        if resp.model != CALIBRATED_FOR:
            logger.warning("occasion_policy_uncalibrated", calibrated_for=CALIBRATED_FOR, answered=resp.model)

        occasion_p = {occ: resp.noul(_occasion_key(occ)).p for occ in Occasion}
        formality = resp.score("formality")
        level = max(0, min(int(Formality.BLACK_TIE), round(formality.score)))
        aesthetic = resp.choice("aesthetic")
        garment_type = resp.choice("garment_type")
        return GarmentJudgment(
            occasion_p=occasion_p,
            occasions=occasions_from(occasion_p),
            formality=Formality(level),
            formality_score=formality.score,
            formality_confidence=formality.confidence,
            aesthetic=Aesthetic(aesthetic.choice),
            aesthetic_confidence=aesthetic.confidence,
            garment_type=garment_type.choice,
            garment_type_confidence=garment_type.confidence,
            garment_type_probabilities=garment_type.probabilities,
            garment_photo_p=resp.noul("garment_photo").p,
            warmth=Warmth(resp.choice("warmth").choice),
            model=resp.model,
            latency_ms=resp.latency_ms,
        )
