"""Gap finder: a hand-built closet with an obvious answer, the counting checked by brute force."""

from __future__ import annotations

from backend.engine.gaps import CANDIDATE_ID, MAX_CANDIDATES, _gap, candidates, find_gaps
from backend.engine.outfits import valid_looks, violations
from backend.schemas.taxonomy import ColorName, Formality, GarmentCategory, Occasion
from evaluation.outfit_engine import demo_closet
from tests.unit.engine.test_outfits import item

# Tops and bottoms, no shoes: every occasion that needs footwear has no outfit, so shoes are the answer.
NO_SHOES = [
    item("t1", "t_shirt", GarmentCategory.TOPWEAR, ColorName.WHITE, "white"),
    item("t2", "shirt", GarmentCategory.TOPWEAR, ColorName.NAVY, "navy", Formality.SMART_CASUAL),
    item("b1", "chinos", GarmentCategory.BOTTOMWEAR, ColorName.BEIGE, "beige", Formality.SMART_CASUAL),
    item("b2", "jeans", GarmentCategory.BOTTOMWEAR, ColorName.BLUE, "blue"),
]


def test_a_closet_without_shoes_is_told_to_buy_shoes() -> None:
    gaps = find_gaps(NO_SHOES)
    assert gaps and gaps[0].example.items  # a non-empty answer with an example
    top = gaps[0]
    assert top.garment_type in {"sneakers", "loafers"}
    assert Occasion.EVERYDAY_CASUAL in top.unlocked
    assert any(i.id == CANDIDATE_ID for i in top.example.items)
    assert violations(top.example, top.example_occasion, None) == []


def test_counts_equal_brute_force_over_the_whole_closet() -> None:
    """The finder drops the candidate's own category to go faster; the counts must not change."""
    closet = demo_closet()[:14]
    had = {o for o in Occasion if valid_looks(closet, o).looks}
    for cand in candidates(closet)[:12]:
        trial = sorted([*closet, cand], key=lambda i: i.id)
        expected = {
            frozenset(i.id for i in g)
            for o in Occasion
            for g in valid_looks(trial, o).looks
            if any(i.id == CANDIDATE_ID for i in g)
        }
        gap = _gap(closet, cand, had)
        assert (gap.new_outfits if gap else 0) == len(expected), cand.short_label


def test_candidates_skip_owned_items_and_what_the_buyer_would_not_wear() -> None:
    closet = demo_closet()
    owned = {(i.garment_type, i.color_family) for i in closet}
    for buyer in ("all", "menswear", "womenswear"):
        found = candidates(closet, buyer)
        assert 0 < len(found) <= MAX_CANDIDATES
        assert not {(c.garment_type, c.color_family) for c in found} & owned
    assert not {c.garment_type for c in candidates(closet, "menswear")} & {"dress", "skirt", "blouse"}


def test_demo_closet_gets_three_different_types_deterministically() -> None:
    first, second = find_gaps(demo_closet()), find_gaps(demo_closet())
    assert [g.label for g in first] == [g.label for g in second]
    assert len(first) == 3 and len({g.garment_type for g in first}) == 3
    assert [g.new_outfits for g in first] == sorted((g.new_outfits for g in first), reverse=True)
    for g in first:
        assert g.new_outfits > 0 and violations(g.example, g.example_occasion, None) == []


def test_a_mens_suggestion_never_uses_a_skirt_or_dress_from_the_closet() -> None:
    for gap in find_gaps(demo_closet(), "menswear"):
        assert not {i.garment_type for i in gap.example.items} & {"skirt", "dress", "blouse", "lehenga"}
