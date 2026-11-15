"""Perception: the code steps around describe → judge, the rejections, the cache. Models are mocked."""

from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from PIL import Image

from backend.schemas.perception import Warmth
from backend.schemas.taxonomy import Aesthetic, ColorName, Formality, GarmentCategory, Occasion, PatternName
from backend.services.garment_description import VisualDescription, VLMUnavailableError
from backend.services.garment_judge import GarmentJudgment
from backend.services.image_guard import GuardOutcome, UnusableImageError
from backend.services.jev import JevUnavailableError
from backend.services.perception import Perceiver, PerceptionError, category_of, pattern_from_words, tags_from

VLM = VisualDescription(
    is_clothing_photo=True,
    item="linen shirt",
    colours=["navy"],
    pattern="solid",
    fabric="linen",
    other_garments=["white price tag", "beige chinos"],
    subject="a navy linen shirt",
    cost_usd=0.0002,
)

JUDGMENT = GarmentJudgment(
    occasion_p={Occasion.SMART_CASUAL: 0.9, Occasion.DATE_NIGHT: 0.8},
    occasions=[Occasion.SMART_CASUAL, Occasion.DATE_NIGHT],
    formality=Formality.SMART_CASUAL,
    formality_score=2.1,
    formality_confidence=0.9,
    aesthetic=Aesthetic.CLASSIC,
    aesthetic_confidence=0.8,
    garment_type="shirt",
    garment_type_confidence=0.95,
    garment_type_probabilities={"shirt": 0.95},
    garment_photo_p=0.97,
    warmth=Warmth.LIGHT,
    model="jev-1.13.0",
    latency_ms=400.0,
)


def _photo() -> Image.Image:
    """A navy garment on a light backdrop, textured enough to pass the blur check."""
    rng = np.random.default_rng(1)
    arr = np.full((300, 300, 3), 230, dtype=np.uint8)
    arr[50:250, 60:240] = (25, 35, 80)
    arr = np.clip(arr.astype(int) + rng.integers(-12, 12, arr.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _bytes(img: Image.Image) -> bytes:
    out = BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def test_both_replies_become_tags() -> None:
    tags = tags_from(VLM, JUDGMENT, _photo())
    assert tags.garment_type == "shirt"
    assert tags.category == GarmentCategory.TOPWEAR
    assert tags.color_family == "navy" and tags.color_hex.startswith("#")
    assert tags.formality == Formality.SMART_CASUAL
    assert tags.warmth == Warmth.LIGHT
    assert tags.occasions == [Occasion.SMART_CASUAL, Occasion.DATE_NIGHT]
    assert tags.item_count == 2  # the price tag is not a garment; the chinos are
    assert tags.short_label.endswith("linen shirt")


def test_a_type_outside_the_taxonomy_becomes_other() -> None:
    tags = tags_from(VLM, replace(JUDGMENT, garment_type="space_suit"), _photo())
    assert tags.garment_type == "other"
    assert tags.category == GarmentCategory.OTHER


def test_no_colour_word_lets_the_pixels_name_it() -> None:
    assert tags_from(replace(VLM, colours=[]), JUDGMENT, _photo()).color == ColorName.NAVY


@pytest.mark.parametrize(
    ("vlm", "judgment"),
    [
        (replace(VLM, is_clothing_photo=False, subject="a red car"), JUDGMENT),
        (replace(VLM, subject="a red car"), replace(JUDGMENT, garment_photo_p=0.1)),
    ],
)
def test_a_non_clothing_photo_is_rejected(vlm: VisualDescription, judgment: GarmentJudgment) -> None:
    with pytest.raises(UnusableImageError) as info:
        tags_from(vlm, judgment, _photo())
    assert info.value.decision.outcome == GuardOutcome.REJECT
    assert "a red car" in info.value.message


def test_an_unsure_judgment_still_tags_the_photo() -> None:
    assert tags_from(VLM, replace(JUDGMENT, garment_photo_p=0.6), _photo()).garment_type == "shirt"


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("solid", PatternName.SOLID),
        (None, PatternName.SOLID),
        ("navy and white checked", PatternName.CHECKERED),
        ("printed graphic", PatternName.GRAPHIC_PRINT),
        ("polka dots", PatternName.POLKA_DOT),
        ("sequinned", PatternName.OTHER),
    ],
)
def test_pattern_words_map_onto_the_taxonomy(words: str | None, expected: PatternName) -> None:
    assert pattern_from_words(words) == expected


def test_accessories_and_footwear_get_their_category() -> None:
    assert category_of("belt") == GarmentCategory.ACCESSORY
    assert category_of("loafers") == GarmentCategory.FOOTWEAR
    assert category_of("dress") == GarmentCategory.FULLBODY
    assert category_of("other") == GarmentCategory.OTHER


def test_a_judgment_survives_the_cache_round_trip() -> None:
    restored = GarmentJudgment.from_json(json.loads(json.dumps(JUDGMENT.to_json())))
    assert restored == JUDGMENT


def _perceiver(vlm: Any = VLM, judgment: Any = JUDGMENT, cache: Any = None) -> tuple[Perceiver, AsyncMock, AsyncMock]:
    describe = AsyncMock(side_effect=vlm) if isinstance(vlm, Exception) else AsyncMock(return_value=vlm)
    judge = AsyncMock(side_effect=judgment) if isinstance(judgment, Exception) else AsyncMock(return_value=judgment)
    describer, judge_client = MagicMock(), MagicMock()
    describer.describe, judge_client.judge = describe, judge
    return Perceiver(describer=describer, judge=judge_client, cache=cache), describe, judge


async def test_perceive_runs_both_calls_and_caches_plain_json() -> None:
    cache = MagicMock()
    cache.get, cache.set = AsyncMock(return_value=None), AsyncMock()
    perceiver, describe, judge = _perceiver(cache=cache)
    assert (await perceiver.perceive(_bytes(_photo()))).garment_type == "shirt"
    describe.assert_awaited_once()
    assert judge.await_args.args[0].to_state()["garment"] == "linen shirt"
    stored = cache.set.await_args.args[1]
    json.dumps(stored)  # must be storable in a JSONB column


async def test_a_cached_photo_costs_no_call() -> None:
    from dataclasses import asdict

    cache = MagicMock()
    cache.get = AsyncMock(return_value={"description": asdict(VLM), "judgment": JUDGMENT.to_json()})
    cache.set = AsyncMock()
    perceiver, describe, judge = _perceiver(cache=cache)
    assert (await perceiver.perceive(_bytes(_photo()))).garment_type == "shirt"
    describe.assert_not_awaited()
    judge.assert_not_awaited()


@pytest.mark.parametrize(
    ("vlm", "judgment"),
    [(VLMUnavailableError("timed out"), JUDGMENT), (VLM, JevUnavailableError("down"))],
)
async def test_a_model_failure_is_a_perception_error(vlm: Any, judgment: Any) -> None:
    perceiver, _, _ = _perceiver(vlm, judgment)
    with pytest.raises(PerceptionError):
        await perceiver.perceive(_bytes(_photo()))


async def test_a_blank_photo_is_refused_before_any_paid_call() -> None:
    perceiver, describe, judge = _perceiver()
    with pytest.raises(UnusableImageError) as info:
        await perceiver.perceive(_bytes(Image.new("RGB", (300, 300), (200, 200, 200))))
    assert info.value.decision.outcome == GuardOutcome.RETAKE
    describe.assert_not_awaited()
    judge.assert_not_awaited()


async def test_a_file_that_is_not_an_image_is_a_clear_error() -> None:
    perceiver, _, _ = _perceiver()
    with pytest.raises(PerceptionError, match="not an image"):
        await perceiver.perceive(b"not an image")
