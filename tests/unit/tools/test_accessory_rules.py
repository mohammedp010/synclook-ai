"""Tests for the accessory rule engine — candidates and coherence.

What is pinned here is the rules themselves (a tie needs a collared shirt,
metals agree, leather follows the shoes).
"""

from __future__ import annotations

import pytest

from backend.schemas.clothing import ClothingType
from backend.schemas.taxonomy import AccessoryType, Formality, Occasion
from backend.tools.accessory_rules import (
    ACCESSORY_RULES,
    OCCASION_FORMALITY,
    AccessoryCandidate,
    AccessoryContext,
    as_accessory,
    candidates,
    coherence_issues,
)


def _ctx(
    base_type: ClothingType = ClothingType.SHIRT,
    garment: str = "shirt",
    color: str = "navy",
    formality: Formality = Formality.SMART_CASUAL,
    occasion: Occasion | None = None,
    intent: str = "unisex",
) -> AccessoryContext:
    return AccessoryContext(
        base_type=base_type,
        base_garment=garment,
        base_color=color,
        formality=formality,
        occasion=occasion,
        shopping_intent=intent,
    )


def _names(cands: list[AccessoryCandidate]) -> set[str]:
    return {c.accessory.value for c in cands}


# ── Vocabulary ───────────────────────────────────────────────────────


def test_every_rule_has_a_band_inside_the_ladder() -> None:
    for accessory, rule in ACCESSORY_RULES.items():
        low, high = rule.formality
        assert low <= high, accessory
    assert AccessoryType.SOCKS not in ACCESSORY_RULES  # recognised, never suggested


@pytest.mark.parametrize("occasion", list(Occasion))
def test_every_occasion_has_a_register(occasion: Occasion) -> None:
    assert occasion in OCCASION_FORMALITY


def test_as_accessory_reads_values_and_words() -> None:
    assert as_accessory("pocket_square") == AccessoryType.POCKET_SQUARE
    assert as_accessory("pocket square") == AccessoryType.POCKET_SQUARE
    assert as_accessory("shirt") is None
    assert as_accessory("other") is None


# ── Candidates ───────────────────────────────────────────────────────


def test_formal_menswear_gets_tailoring_pieces_not_casual_ones() -> None:
    ctx = _ctx(formality=Formality.BUSINESS_FORMAL, occasion=Occasion.INTERVIEW, intent="menswear")
    names = _names(candidates(ctx))
    assert {"tie", "watch", "belt", "briefcase"} <= names
    assert not names & {"cap", "sunglasses", "backpack", "earrings"}


def test_gym_gets_sport_pieces() -> None:
    names = _names(candidates(_ctx(ClothingType.HOODIE, "hoodie", "grey", Formality.CASUAL, Occasion.GYM_ATHLEISURE)))
    assert {"cap", "backpack"} <= names
    assert not names & {"tie", "belt", "cufflinks", "necklace"}


def test_loungewear_gets_nothing() -> None:
    assert candidates(_ctx(formality=Formality.LOUNGE, occasion=Occasion.LOUNGEWEAR)) == []


def test_unisex_with_a_neutral_garment_suggests_only_neutral_pieces() -> None:
    # "unisex" means the suggestion has to work for anyone.
    names = _names(candidates(_ctx(formality=Formality.BUSINESS_FORMAL, occasion=Occasion.WEDDING_GUEST)))
    assert not names & {"tie", "earrings", "clutch", "pocket_square"}


def test_the_garment_can_supply_the_lean() -> None:
    ctx = _ctx(ClothingType.DRESS, "dress", "red", Formality.BUSINESS_FORMAL, Occasion.WEDDING_GUEST)
    dress = _names(candidates(ctx))
    assert {"earrings", "clutch"} <= dress
    assert "tie" not in dress


def test_explicit_intent_beats_the_garment() -> None:
    names = _names(candidates(_ctx(formality=Formality.BUSINESS_FORMAL, intent="womenswear")))
    assert "tie" not in names and "earrings" in names


def test_dupatta_only_with_a_kurta_set() -> None:
    kurta = _ctx(ClothingType.SHIRT, "kurta", "maroon", Formality.SMART_CASUAL, Occasion.FESTIVE_ETHNIC, "womenswear")
    assert "dupatta" in _names(candidates(kurta))
    shirt = _ctx(occasion=Occasion.FESTIVE_ETHNIC, intent="womenswear")
    assert "dupatta" not in _names(candidates(shirt))


def test_rules_order_with_occasion_bonus() -> None:
    ranked = candidates(_ctx(formality=Formality.CASUAL, occasion=Occasion.BEACH_RESORT))
    assert ranked[0].accessory == AccessoryType.SUNGLASSES  # made for the beach: 0.75 + 0.15
    assert ranked[0].reason == "made for beach resort"
    assert all(a.score >= b.score for a, b in zip(ranked, ranked[1:]))


def test_accessory_upload_is_not_suggested_back() -> None:
    names = _names(candidates(_ctx(ClothingType.ACCESSORY, "watch", "black", Formality.CASUAL)))
    assert "watch" not in names


# ── Coherence ─────────────────────────────────────────────


def test_coherence_catches_each_broken_rule() -> None:
    ctx = _ctx(formality=Formality.BUSINESS_FORMAL)
    outfit = [("trousers", "grey"), ("shoes", "black")]
    broken = [("belt", "brown"), ("watch", "gold"), ("cufflinks", "silver")]
    details = [d for _, d in coherence_issues(ctx, outfit + broken)]
    assert any("leather should agree" in d for d in details)
    assert any("mixed metal" in d for d in details)
    assert any("more than 2" in d for d in details)

    tee = _ctx(ClothingType.TSHIRT, "t_shirt", "white")
    assert coherence_issues(tee, [("jeans", "blue"), ("tie", "navy")]) == [
        ("tie", "tie without its prerequisite (collared_shirt)")
    ]
