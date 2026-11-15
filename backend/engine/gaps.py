"""The gap finder: which one garment, if bought, unlocks the most new outfits?

Pure code (no model, no network, no database). For each candidate — a short list of
common garment types × the 3 colour families that pair best with the closet — it
pretends the candidate is owned and asks the outfit engine's own rules
(``outfits.valid_looks``) for every valid outfit across all 14 occasions. Every
outfit that contains the candidate is new. A look valid for several occasions counts
once: it is one outfit you can wear to several places.

Weather is left out: a purchase is for the whole year, not for today's forecast.
Outerwear is an optional layer, so a jacket's count is the outfits it can go over.
At most one suggestion per garment type: three colours of one shoe is one idea.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.engine.outfits import (
    _COLOURS,
    _RULES,
    ClosetItem,
    Outfit,
    _coarse,
    _colour,
    _evidence,
    _is_garment,
    _score,
    item_problem,
    valid_looks,
)
from backend.schemas.clothing import Color
from backend.schemas.perception import Warmth
from backend.schemas.taxonomy import COARSE_TYPE, TYPE_CATEGORY, ColorName, Formality, GarmentType, Occasion

MAX_GAPS = 3
MAX_CANDIDATES = 40
COLOURS_PER_TYPE = 3
CANDIDATE_ID = "candidate"

# Common garments a shop sells in every colour, with their usual register and warmth
# (the same warmth defaults the demo closet uses). 13 types × 3 colours = 39 ≤ 40.
_TYPES: dict[GarmentType, tuple[Formality, Warmth]] = {
    GarmentType.T_SHIRT: (Formality.CASUAL, Warmth.LIGHT),
    GarmentType.SHIRT: (Formality.SMART_CASUAL, Warmth.MEDIUM),
    GarmentType.SWEATER: (Formality.CASUAL, Warmth.HEAVY),
    GarmentType.KURTA: (Formality.SMART_CASUAL, Warmth.MEDIUM),
    GarmentType.TROUSERS: (Formality.SMART_CASUAL, Warmth.MEDIUM),
    GarmentType.CHINOS: (Formality.SMART_CASUAL, Warmth.MEDIUM),
    GarmentType.JEANS: (Formality.CASUAL, Warmth.MEDIUM),
    GarmentType.SKIRT: (Formality.SMART_CASUAL, Warmth.LIGHT),
    GarmentType.DRESS: (Formality.SMART_CASUAL, Warmth.MEDIUM),
    GarmentType.BLAZER: (Formality.BUSINESS_FORMAL, Warmth.MEDIUM),
    GarmentType.JACKET: (Formality.CASUAL, Warmth.MEDIUM),
    GarmentType.SNEAKERS: (Formality.CASUAL, Warmth.MEDIUM),
    GarmentType.LOAFERS: (Formality.SMART_CASUAL, Warmth.MEDIUM),
}


@dataclass(frozen=True)
class Gap:
    garment_type: str
    color_family: str
    new_outfits: int
    """Distinct new garment combinations, across all occasions."""
    per_occasion: dict[Occasion, int]
    unlocked: list[Occasion]
    """Occasions the closet had no outfit for, and now has."""
    example: Outfit
    """The best-scoring new outfit, for ``example_occasion``."""
    example_occasion: Occasion

    @property
    def label(self) -> str:
        return f"{self.color_family} {self.garment_type.replace('_', ' ')}"


def _palette(closet: list[ClosetItem]) -> list[Color]:
    """The colour families that pair best, on average, with the closet's garments."""
    owned = [_colour(i) for i in closet if _is_garment(i)]
    if not owned:
        return [Color.WHITE, Color.NAVY, Color.BLACK]

    def fit(c: Color) -> float:
        return sum(max(_COLOURS.score_pair(c, o), _COLOURS.score_pair(o, c)) for o in owned) / len(owned)

    families: list[Color] = [c for c in Color if c != Color.OTHER]
    return sorted(families, key=lambda c: (-fit(c), c.value))[:COLOURS_PER_TYPE]


def candidates(closet: list[ClosetItem], buyer: str = "all") -> list[ClosetItem]:
    """Garment types × palette colours, minus what is already owned and what the buyer would not wear."""
    owned = {(i.garment_type, i.color_family) for i in closet}
    out: list[ClosetItem] = []
    for garment, (formality, warmth) in _TYPES.items():
        if not _RULES.is_item_allowed_for_gender(COARSE_TYPE[garment], buyer):
            continue
        for colour in _palette(closet):
            if (garment.value, colour.value) in owned:
                continue  # a second navy chinos adds near-copies of outfits you have
            label = f"{colour.value} {garment.value.replace('_', ' ')}"
            out.append(
                ClosetItem(
                    id=CANDIDATE_ID,
                    garment_type=garment.value,
                    category=TYPE_CATEGORY[garment],
                    color=ColorName(colour.value),
                    color_family=colour.value,
                    color_hex="",
                    formality=formality,
                    warmth=warmth,
                    short_label=label,
                )
            )
    return out[:MAX_CANDIDATES]


def _gap(closet: list[ClosetItem], candidate: ClosetItem, had: set[Occasion]) -> Gap | None:
    # A look holds at most one item per category, so the other items of the candidate's
    # category can never share a look with it: drop them (same counts, ~10x less work).
    trial = sorted([*(i for i in closet if i.category != candidate.category), candidate], key=lambda i: i.id)
    new: set[frozenset[str]] = set()
    per_occasion: dict[Occasion, int] = {}
    best: tuple[tuple[float, tuple[str, ...]], Outfit, Occasion] | None = None
    for occasion in Occasion:
        if item_problem(candidate, occasion, None) is not None:
            continue  # the item cannot be worn there, so it unlocks nothing there
        looks = [g for g in valid_looks(trial, occasion).looks if any(i.id == CANDIDATE_ID for i in g)]
        if not looks:
            continue
        per_occasion[occasion] = len(looks)
        new.update(frozenset(i.id for i in g) for g in looks)
        for g in looks:
            parts = _score(g, occasion, {}, frozenset())
            score = round(sum(parts.values()), 3)
            rank = (-score, tuple(i.id for i in g))  # highest score, then a fixed order
            if best is None or rank < best[0]:
                best = (rank, Outfit(g, score, parts, _evidence(g, [], occasion, None, frozenset())), occasion)
    if best is None:
        return None
    return Gap(
        garment_type=candidate.garment_type,
        color_family=candidate.color_family,
        new_outfits=len(new),
        per_occasion=per_occasion,
        unlocked=[o for o in per_occasion if o not in had],
        example=best[1],
        example_occasion=best[2],
    )


def find_gaps(closet: list[ClosetItem], buyer: str = "all") -> list[Gap]:
    """The top 3 single purchases by new outfits, at most one per garment type, best first."""
    # The buyer rule applies to the closet too: a men's suggestion is never shown with a skirt.
    items = [i for i in closet if i.id != CANDIDATE_ID and _RULES.is_item_allowed_for_gender(_coarse(i), buyer)]
    had = {o for o in Occasion if valid_looks(sorted(items, key=lambda i: i.id), o).looks}
    best_per_type: dict[str, Gap] = {}
    for candidate in candidates(items, buyer):
        gap = _gap(items, candidate, had)
        if gap is None:
            continue
        current = best_per_type.get(gap.garment_type)
        if current is None or gap.new_outfits > current.new_outfits:
            best_per_type[gap.garment_type] = gap  # three colours of one shoe is one suggestion
    ranked = sorted(best_per_type.values(), key=lambda g: (-g.new_outfits, -len(g.unlocked), g.label))
    return ranked[:MAX_GAPS]
