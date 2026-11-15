"""Outfit engine: property tests over the demo closet and seeded random closets, plus the rules one by one."""

from __future__ import annotations

import random

import pytest

from backend.engine.outfits import (
    MAX_OUTFITS,
    ClosetItem,
    Outfit,
    TempBand,
    Weather,
    build_outfits,
    item_problem,
    violations,
)
from backend.schemas.perception import Warmth
from backend.schemas.taxonomy import ColorName, Formality, GarmentCategory, Occasion, PatternName
from evaluation.outfit_engine import demo_closet

WEATHERS = [None, Weather(6, True), Weather(20, False), Weather(32, False)]
DEMO = demo_closet()


def _closets() -> list[list[ClosetItem]]:
    rng = random.Random(3)
    return [DEMO] + [rng.sample(DEMO, rng.randint(6, len(DEMO))) for _ in range(6)]


def _garment_ids(outfit: Outfit) -> set[str]:
    return {i.id for i in outfit.items if i.category != GarmentCategory.ACCESSORY}


def item(
    id: str,
    garment_type: str,
    category: GarmentCategory,
    color: ColorName = ColorName.NAVY,
    family: str = "navy",
    formality: Formality = Formality.CASUAL,
    warmth: Warmth = Warmth.MEDIUM,
    pattern: PatternName = PatternName.SOLID,
) -> ClosetItem:
    return ClosetItem(
        id=id,
        garment_type=garment_type,
        category=category,
        color=color,
        color_family=family,
        color_hex="#000080",
        pattern=pattern,
        formality=formality,
        warmth=warmth,
        short_label=f"{family} {garment_type.replace('_', ' ')}",
    )


# ── Properties ───────────────────────────────────────────────────────


@pytest.mark.parametrize("closet_n", range(7))
def test_no_rule_broken_no_item_twice_and_only_the_callers_items(closet_n: int) -> None:
    closet = _closets()[closet_n]
    ids = {i.id for i in closet}
    for weather in WEATHERS:
        for occasion in Occasion:
            result = build_outfits(closet, occasion, weather)
            assert result.outfits or result.reason
            assert len(result.outfits) <= MAX_OUTFITS
            for outfit in result.outfits:
                assert violations(outfit, occasion, weather) == []
                assert len(set(outfit.item_ids)) == len(outfit.item_ids)
                assert set(outfit.item_ids) <= ids
                assert outfit.evidence


def test_same_input_same_output_whatever_the_order() -> None:
    shuffled = DEMO[:]
    random.Random(1).shuffle(shuffled)
    for occasion in Occasion:
        first = build_outfits(DEMO, occasion, Weather(20, True))
        again = build_outfits(shuffled, occasion, Weather(20, True))
        assert [o.item_ids for o in first.outfits] == [o.item_ids for o in again.outfits]
        assert [o.evidence for o in first.outfits] == [o.evidence for o in again.outfits]


def test_the_three_outfits_differ_by_at_least_two_garments() -> None:
    for occasion in Occasion:
        outfits = build_outfits(DEMO, occasion).outfits
        for n, a in enumerate(outfits):
            for b in outfits[n + 1 :]:
                ga, gb = _garment_ids(a), _garment_ids(b)
                assert max(len(ga - gb), len(gb - ga)) >= 2


def test_the_demo_closet_serves_every_occasion_it_can_with_three() -> None:
    # The demo has one pair of shorts (the only bottom allowed for lounge and gym) and
    # one pair of sneakers (the gym's only shoes), so those two get one look each.
    for occasion in Occasion:
        n = len(build_outfits(DEMO, occasion).outfits)
        assert n == (1 if occasion in (Occasion.LOUNGEWEAR, Occasion.GYM_ATHLEISURE) else 3), occasion


# ── Rules ────────────────────────────────────────────────────────────

TEE = item("tee", "t_shirt", GarmentCategory.TOPWEAR, warmth=Warmth.LIGHT)
SHIRT = item("shirt", "shirt", GarmentCategory.TOPWEAR, ColorName.WHITE, "white", Formality.BUSINESS_FORMAL)
JEANS = item("jeans", "jeans", GarmentCategory.BOTTOMWEAR, ColorName.DENIM_BLUE, "blue")
TROUSERS = item("trousers", "trousers", GarmentCategory.BOTTOMWEAR, ColorName.GREY, "grey", Formality.BUSINESS_FORMAL)
SNEAKERS = item("sneakers", "sneakers", GarmentCategory.FOOTWEAR, ColorName.WHITE, "white")
LOAFERS = item("loafers", "loafers", GarmentCategory.FOOTWEAR, ColorName.BLACK, "black", Formality.BUSINESS_FORMAL)
COAT = item("coat", "coat", GarmentCategory.OUTERWEAR, ColorName.CAMEL, "brown", Formality.SMART_CASUAL, Warmth.HEAVY)
SHORTS = item("shorts", "shorts", GarmentCategory.BOTTOMWEAR, warmth=Warmth.LIGHT)


def test_no_footwear_is_a_clear_reason() -> None:
    result = build_outfits([TEE, JEANS], Occasion.EVERYDAY_CASUAL)
    assert result.outfits == []
    assert result.reason is not None and "no footwear in the closet" in result.reason


def test_formality_keeps_sneakers_out_of_an_interview() -> None:
    result = build_outfits([SHIRT, TROUSERS, SNEAKERS], Occasion.INTERVIEW)
    assert result.outfits == []
    assert result.reason is not None and "white sneakers: formality 1, interview needs 2–4" in result.reason
    assert build_outfits([SHIRT, TROUSERS, SNEAKERS, LOAFERS], Occasion.INTERVIEW).outfits


def test_the_occasion_decides_the_items() -> None:
    assert item_problem(JEANS, Occasion.INTERVIEW, None) == "blue jeans: not worn to interview"
    lehenga = item("l", "lehenga", GarmentCategory.FULLBODY, formality=Formality.BUSINESS_FORMAL)
    assert "ceremonial" in (item_problem(lehenga, Occasion.INTERVIEW, None) or "")
    assert item_problem(lehenga, Occasion.WEDDING_GUEST, None) is None


def test_the_gym_takes_sports_shoes_only() -> None:
    boots = item("boots", "boots", GarmentCategory.FOOTWEAR, ColorName.BLACK, "black")
    assert item_problem(boots, Occasion.GYM_ATHLEISURE, None) == "black boots: not sports shoes"
    assert item_problem(SNEAKERS, Occasion.GYM_ATHLEISURE, None) is None


def test_loungewear_needs_no_shoes() -> None:
    (outfit,) = build_outfits([TEE, SHORTS, SNEAKERS], Occasion.LOUNGEWEAR).outfits
    assert outfit.item_ids == ("tee", "shorts")


def test_cold_or_rain_adds_the_outerwear_and_drops_light_bottoms() -> None:
    cold = Weather(5, False)
    assert cold.band == TempBand.COLD
    outfits = build_outfits([TEE, JEANS, SHORTS, SNEAKERS, COAT], Occasion.EVERYDAY_CASUAL, cold).outfits
    assert outfits and all("coat" in o.item_ids and "shorts" not in o.item_ids for o in outfits)
    rainy = build_outfits([TEE, JEANS, SNEAKERS, COAT], Occasion.EVERYDAY_CASUAL, Weather(20, True)).outfits
    assert all("coat" in o.item_ids for o in rainy)


def test_cold_without_outerwear_keeps_the_light_top_out_but_says_so() -> None:
    sweater = item("sweater", "sweater", GarmentCategory.TOPWEAR, warmth=Warmth.HEAVY)
    result = build_outfits([TEE, sweater, JEANS, SNEAKERS], Occasion.EVERYDAY_CASUAL, Weather(4, True))
    assert [o.item_ids[0] for o in result.outfits] == ["sweater"]
    assert any("no outerwear" in note for note in result.notes)


def test_heat_drops_heavy_pieces_and_outerwear() -> None:
    hoodie = item("hoodie", "hoodie", GarmentCategory.TOPWEAR, warmth=Warmth.HEAVY)
    outfits = build_outfits([TEE, hoodie, JEANS, SNEAKERS, COAT], Occasion.EVERYDAY_CASUAL, Weather(33, False)).outfits
    assert [o.item_ids for o in outfits] == [("tee", "jeans", "sneakers")]


def test_two_patterns_do_not_mix() -> None:
    striped = item("st", "t_shirt", GarmentCategory.TOPWEAR, pattern=PatternName.STRIPED)
    checked = item("ch", "jeans", GarmentCategory.BOTTOMWEAR, pattern=PatternName.CHECKERED)
    result = build_outfits([striped, checked, SNEAKERS], Occasion.EVERYDAY_CASUAL)
    assert result.outfits == [] and result.reason is not None and "do not combine" in result.reason


def test_owned_accessories_must_agree_with_the_look() -> None:
    brown_belt = item("belt", "belt", GarmentCategory.ACCESSORY, ColorName.BROWN, "brown")
    black_belt = item("belt2", "belt", GarmentCategory.ACCESSORY, ColorName.BLACK, "black")
    (outfit,) = build_outfits([SHIRT, TROUSERS, LOAFERS, brown_belt, black_belt], Occasion.INTERVIEW).outfits
    assert "belt2" in outfit.item_ids and "belt" not in outfit.item_ids  # leather follows the black shoes


def test_recently_worn_and_preference_move_the_ranking() -> None:
    jeans2 = item("jeans2", "jeans", GarmentCategory.BOTTOMWEAR, ColorName.CHARCOAL, "grey")
    sneakers2 = item("sneakers2", "sneakers", GarmentCategory.FOOTWEAR, ColorName.BLACK, "black")
    closet = [TEE, JEANS, jeans2, SNEAKERS, sneakers2]
    top = build_outfits(closet, Occasion.EVERYDAY_CASUAL).outfits[0]
    worn = build_outfits(closet, Occasion.EVERYDAY_CASUAL, recently_worn=top.item_ids[1:]).outfits[0]
    assert worn.item_ids != top.item_ids and worn.score_parts["recently_worn"] > -0.3
    liked = build_outfits(closet, Occasion.EVERYDAY_CASUAL, preferences={"jeans2": 1.0}).outfits[0]
    assert "jeans2" in liked.item_ids


def test_scores_are_rule_parts_not_confidence() -> None:
    outfit = build_outfits(DEMO, Occasion.SMART_CASUAL).outfits[0]
    assert set(outfit.score_parts) == {"colour_harmony", "formality_fit", "preference", "recently_worn"}
    assert outfit.score == pytest.approx(sum(outfit.score_parts.values()), abs=1e-3)
