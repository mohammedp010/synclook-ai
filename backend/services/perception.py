"""Perception: a garment photo → validated ``GarmentTags``.

Two calls, each doing what it was measured best at (``evaluation/perception.py``,
public split, owner's decision 2026-11-15):

1. **Describe** — the vision model writes what it sees, in words
   (``garment_description``: item, colours, fabric, pattern, other items).
2. **Judge** — Jev reads those words and answers typed questions
   (``garment_judge``): garment type, formality, occasions, warmth, and
   "is this photo about clothing?".

Against one structured vision call (arm A), this beat it on formality (0.727
vs 0.676, past the 3-point bar fixed before the run) and caught more
non-clothing photos; it lost on occasions and pattern, and costs about twice as
much. Code then fills the rest:

- **Colour:** the model's colour word picks the family; ``color_extraction``
  measures the pixels for the exact shade and hex (commit 2c9bf9c).
- **Category** comes from the garment type; **pattern** from the describer's
  pattern words; **item count** from the describer's other items, minus parts
  and tags; **short label** from colour and item.
- **Rejection:** a non-clothing photo raises ``UnusableImageError`` (the 422
  the upload guard always gave). Blurred, dark, blank and tiny photos are
  refused before any paid call.
- **Cache:** both replies are cached in ``kv_cache`` by the image's SHA-256 and
  both prompt versions, so a re-upload costs nothing. Replies are cached, not
  tags, so a change to the code steps applies to cached photos too.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from enum import Enum
from io import BytesIO
from typing import Any

from PIL import Image

from backend.core.config import Settings, get_settings
from backend.core.exceptions import SynclookError
from backend.core.logging import get_logger
from backend.schemas.perception import GarmentTags
from backend.schemas.taxonomy import (
    COARSE_COLOR,
    GARMENT_TYPE_OPTIONS,
    TYPE_CATEGORY,
    AccessoryType,
    ColorName,
    GarmentCategory,
    GarmentType,
    PatternName,
)
from backend.services.cache import KvCache
from backend.services.color_extraction import FusedColor, extract_colors, name_from_description
from backend.services.color_palette import colour_from_words
from backend.services.garment_description import PROMPT_VERSION as DESCRIBE_VERSION
from backend.services.garment_description import GarmentDescriber, VisualDescription, VLMUnavailableError
from backend.services.garment_judge import QUESTIONS_VERSION, GarmentJudge, GarmentJudgment, description_from
from backend.services.image_guard import GuardOutcome, UnusableImageError, decide, quality_report, separate_items
from backend.services.jev import JevError

logger = get_logger(__name__)

_MAX_LABEL = 60

# The describer's pattern words → the taxonomy (first match wins, so specific words come first).
_PATTERN_WORDS: tuple[tuple[str, PatternName], ...] = (
    ("tie-dye", PatternName.TIE_DYE),
    ("tie dye", PatternName.TIE_DYE),
    ("colour block", PatternName.COLOR_BLOCK),
    ("color block", PatternName.COLOR_BLOCK),
    ("polka", PatternName.POLKA_DOT),
    ("plaid", PatternName.PLAID),
    ("tartan", PatternName.PLAID),
    ("check", PatternName.CHECKERED),
    ("stripe", PatternName.STRIPED),
    ("floral", PatternName.FLORAL),
    ("camo", PatternName.CAMOUFLAGE),
    ("embroider", PatternName.EMBROIDERED),
    ("leopard", PatternName.ANIMAL_PRINT),
    ("animal", PatternName.ANIMAL_PRINT),
    ("geometric", PatternName.GEOMETRIC),
    ("abstract", PatternName.ABSTRACT),
    ("graphic", PatternName.GRAPHIC_PRINT),
    ("print", PatternName.GRAPHIC_PRINT),
    ("dot", PatternName.POLKA_DOT),
    ("solid", PatternName.SOLID),
    ("plain", PatternName.SOLID),
)


class PerceptionError(SynclookError):
    """A model could not be asked or did not answer; the photo was not tagged."""


def _member[E: Enum](enum: type[E], value: Any) -> E | None:
    try:
        return enum(value)
    except (ValueError, TypeError):
        return None


def category_of(garment_type: str) -> GarmentCategory:
    accessory = _member(AccessoryType, garment_type)
    if accessory is not None and accessory != AccessoryType.OTHER:
        return GarmentCategory.ACCESSORY
    garment = _member(GarmentType, garment_type)
    return TYPE_CATEGORY.get(garment, GarmentCategory.OTHER) if garment is not None else GarmentCategory.OTHER


def pattern_from_words(text: str | None) -> PatternName:
    lowered = (text or "").lower()
    if not lowered:
        return PatternName.SOLID
    return next((p for word, p in _PATTERN_WORDS if word in lowered), PatternName.OTHER)


def measured_colour(vlm: VisualDescription, image: Image.Image) -> FusedColor:
    """The describer's colour word names the family; the pixels name the shade and hex."""
    word: ColorName | None = colour_from_words(vlm.colours[0]) if vlm.colours else None
    reading = extract_colors(image)
    return name_from_description(reading, word or reading.primary)


def tags_from(vlm: VisualDescription, judgment: GarmentJudgment, image: Image.Image) -> GarmentTags:
    """The code steps after both calls. Raises ``UnusableImageError`` for a non-clothing photo."""
    others = separate_items(vlm.other_garments)
    garment_p = judgment.garment_photo_p if vlm.is_clothing_photo else 0.0
    decision = decide(
        quality_report(image), jev_garment_p=garment_p, subject=vlm.subject, garment_count=1 + len(others)
    )
    if decision.outcome in (GuardOutcome.REJECT, GuardOutcome.RETAKE):
        raise UnusableImageError(decision)

    garment_type = judgment.garment_type if judgment.garment_type in GARMENT_TYPE_OPTIONS else "other"
    colour = measured_colour(vlm, image)
    item = " ".join((vlm.item or garment_type.replace("_", " ")).split())
    return GarmentTags(
        garment_type=garment_type,
        category=category_of(garment_type),
        color=colour.name,
        color_family=COARSE_COLOR[colour.name],
        color_hex=colour.hex,
        secondary_color=colour.secondary if colour.secondary != colour.name else None,
        pattern=pattern_from_words(vlm.pattern),
        formality=judgment.formality,
        warmth=judgment.warmth,
        occasions=judgment.occasions,
        short_label=f"{colour.name.value.replace('_', ' ')} {item}"[:_MAX_LABEL],
        item_count=1 + len(others),
    )


class Perceiver:
    """Describe → judge → code steps, with the cache and the usability check around them."""

    def __init__(
        self,
        settings: Settings | None = None,
        describer: GarmentDescriber | None = None,
        judge: GarmentJudge | None = None,
        cache: KvCache | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._describer = describer or GarmentDescriber(self._settings)
        self._judge = judge or GarmentJudge()
        self._cache = cache

    async def replies(self, image_bytes: bytes, image: Image.Image) -> tuple[VisualDescription, GarmentJudgment]:
        """Both paid calls. Raises ``PerceptionError`` when either model fails."""
        try:
            vlm = await self._describer.describe(image_bytes)
        except VLMUnavailableError as exc:
            raise PerceptionError(exc.message) from exc
        try:
            judgment = await self._judge.judge(description_from(vlm, measured_colour(vlm, image).name.value))
        except JevError as exc:
            raise PerceptionError(f"The garment judge failed: {exc}") from exc
        return vlm, judgment

    async def perceive(self, image_bytes: bytes) -> GarmentTags:
        try:
            image = Image.open(BytesIO(image_bytes))
            image.load()
        except Exception as exc:
            raise PerceptionError("That file is not an image we can read") from exc

        quality = quality_report(image)
        if quality.problems:
            raise UnusableImageError(decide(quality))

        digest = hashlib.sha256(image_bytes).hexdigest()
        key = f"perception:{DESCRIBE_VERSION}:{self._settings.vlm_model}:{QUESTIONS_VERSION}:{digest}"
        cached = await self._cache.get(key) if self._cache is not None else None
        if cached is not None:
            vlm, judgment = VisualDescription(**cached["description"]), GarmentJudgment.from_json(cached["judgment"])
        else:
            vlm, judgment = await self.replies(image_bytes, image)
            if self._cache is not None:
                value = {"description": asdict(vlm), "judgment": judgment.to_json()}
                await self._cache.set(key, value, self._settings.perception_cache_ttl_seconds)

        tags = tags_from(vlm, judgment, image)
        logger.info(
            "perceived",
            cached=cached is not None,
            garment_type=tags.garment_type,
            color=tags.color.value,
            vlm_cost_usd=vlm.cost_usd,
            vlm_ms=vlm.latency_ms,
            jev_ms=judgment.latency_ms,
        )
        return tags
