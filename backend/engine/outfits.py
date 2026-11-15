"""The outfit engine: closet items + occasion + weather → up to 3 valid outfits.

Pure code (no model, no network, no database). Every rule it applies already
existed in ``tools/style_rules.py`` and ``tools/accessory_rules.py``; this module
only decides how they combine on items the user owns:

1. **Item rules** — each item must be allowed for the occasion
   (``OCCASION_ALLOWED_ITEMS``), sit within one step of the occasion's formality
   (``OCCASION_FORMALITY``), pass the occasion × formality colour policy, and suit
   the weather (warmth against the temperature band).
2. **Pair rules** — every two garments must be a known pairing (``ITEM_PAIRINGS``)
   and their patterns must mix (``PATTERN_PAIRS``).
3. **Structure** — (top + bottom + footwear) or (one-piece + footwear), optional
   outerwear (wanted when it is cold or raining), then up to two owned accessories
   that pass the accessory coordination rules.
4. **Score** — colour harmony (``ColorMatcherTool``) + formality fit + a preference
   hook (neutral until Phase 5) − a small penalty per recently worn item. The top 3
   that differ by at least two garments are returned, each with its evidence.

The Jev ``occasions`` tag is deliberately not a filter: on the public split it said
yes to nearly everything (precision 0.35, recall 0.94). Formality and the occasion
item rules carry that decision instead.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from itertools import combinations, product

from backend.core.accessory_policy import MAX_ACCESSORIES_PER_LOOK
from backend.schemas.clothing import ClothingType, Color, Pattern
from backend.schemas.perception import GarmentTags, Warmth
from backend.schemas.taxonomy import (
    COARSE_PATTERN,
    COARSE_TYPE,
    Formality,
    GarmentCategory,
    GarmentType,
    Occasion,
    PatternName,
)
from backend.tools.accessory_rules import (
    OCCASION_FORMALITY,
    AccessoryContext,
    as_accessory,
    candidates,
    coherence_issues,
)
from backend.tools.color_matcher import ColorMatcherTool
from backend.tools.style_rules import OCCASION_ALLOWED_ITEMS, StyleRuleEngineTool

MAX_OUTFITS = 3
MIN_DIFFERENT_GARMENTS = 2
FORMALITY_TOLERANCE = 1
"""Steps on the 0–4 ladder an item may sit from the occasion's register. One step
absorbs the perception error (formality MAE 0.28) without letting sneakers into an
interview (1 vs 3)."""

# Score weights. Hand-set, not fitted: colour and formality are each 0–1; preference
# (-1..1) counts half; each recently worn item costs 0.15.
PREFERENCE_WEIGHT = 0.5
RECENTLY_WORN_PENALTY = 0.15

COLD_BELOW_C = 12.0
HOT_FROM_C = 26.0

_CEREMONIAL = frozenset({"lehenga", "saree", "sherwani", "gown"})
"""Ceremonial dress the coarse rules cannot see: all map to ``dress`` or ``suit``,
which an interview allows. Worn only where ceremony is the point."""
_CEREMONIAL_OCCASIONS = frozenset({Occasion.WEDDING_GUEST, Occasion.FESTIVE_ETHNIC, Occasion.COCKTAIL_SEMI_FORMAL})

_SPORTS_SHOES = frozenset({"sneakers", "sports_shoes"})
"""The coarse rules see one ``shoes`` type, so boots and sandals reached the gym; the
LLM judge flagged both (2026-11-15)."""

_RULES = StyleRuleEngineTool()
_COLOURS = ColorMatcherTool()


class ClosetItem(GarmentTags):
    """A closet item as the engine sees it: the stored tags plus the row id."""

    id: str


class TempBand(str, Enum):
    COLD = "cold"
    MILD = "mild"
    HOT = "hot"


@dataclass(frozen=True)
class Weather:
    temperature_c: float
    rain: bool

    @property
    def band(self) -> TempBand:
        if self.temperature_c < COLD_BELOW_C:
            return TempBand.COLD
        if self.temperature_c >= HOT_FROM_C:
            return TempBand.HOT
        return TempBand.MILD

    @property
    def wants_outerwear(self) -> bool:
        return self.rain or self.band == TempBand.COLD

    def describe(self) -> str:
        return f"{self.temperature_c:.0f}°C, {self.band.value}{', rain' if self.rain else ''}"


@dataclass(frozen=True)
class Outfit:
    items: tuple[ClosetItem, ...]
    """Garments first (top or one-piece, bottom, outerwear, footwear), then accessories."""
    score: float
    score_parts: dict[str, float]
    evidence: tuple[str, ...]

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.items)


@dataclass(frozen=True)
class OutfitResult:
    outfits: list[Outfit]
    reason: str | None = None
    """Why there are fewer than ``MAX_OUTFITS`` outfits (None when there are 3)."""
    notes: list[str] = field(default_factory=list)
    """Caveats that did not block an outfit (e.g. rain but no outerwear in the closet)."""
    missing: list[str] = field(default_factory=list)
    """Items the user asked for that the closet does not have (``engine.requests``); set by the toolkit."""


# ──────────────────────────────────────────────────────────────────────
#  Item facts
# ──────────────────────────────────────────────────────────────────────


def _coarse_of(garment_type: str) -> str:
    """The live ``ClothingType`` value the style rules speak, or the accessory name."""
    if garment_type in GarmentType._value2member_map_:
        return COARSE_TYPE[GarmentType(garment_type)]
    return garment_type


def _coarse(item: ClosetItem) -> str:
    return _coarse_of(item.garment_type)


def _clothing_type_of(garment_type: str) -> ClothingType:
    coarse = _coarse_of(garment_type)
    return ClothingType(coarse) if coarse in ClothingType._value2member_map_ else ClothingType.ACCESSORY


def _clothing_type(item: ClosetItem) -> ClothingType:
    return _clothing_type_of(item.garment_type)


def _colour(item: ClosetItem) -> Color:
    return Color(item.color_family) if item.color_family in Color._value2member_map_ else Color.OTHER


def _pattern(item: ClosetItem) -> Pattern:
    return Pattern(COARSE_PATTERN[item.pattern])


def _label(occasion: Occasion) -> str:
    return occasion.value.replace("_", " ")


def _formality(level: int) -> str:
    return Formality(level).name.lower().replace("_", "-")


def _target(occasion: Occasion) -> Formality:
    return OCCASION_FORMALITY[occasion]


def item_problem(item: ClosetItem, occasion: Occasion, weather: Weather | None) -> str | None:
    """Why this item cannot be worn for the occasion and weather, or None when it can."""
    name = item.short_label
    if not _RULES.is_item_allowed_for_occasion(occasion, _coarse(item)):
        return f"{name}: not worn to {_label(occasion)}"
    if item.garment_type in _CEREMONIAL and occasion not in _CEREMONIAL_OCCASIONS:
        return f"{name}: ceremonial dress, kept for weddings and festivals"
    if occasion == Occasion.GYM_ATHLEISURE and item.category == GarmentCategory.FOOTWEAR:
        if item.garment_type not in _SPORTS_SHOES:
            return f"{name}: not sports shoes"
    if item.category == GarmentCategory.ACCESSORY:
        return None  # accessories have their own formality bands (accessory_rules)
    target = _target(occasion)
    if abs(item.formality - target) > FORMALITY_TOLERANCE:
        low, high = max(target - FORMALITY_TOLERANCE, 0), min(target + FORMALITY_TOLERANCE, 4)
        return f"{name}: formality {int(item.formality)}, {_label(occasion)} needs {low}–{high}"
    slot = _RULES.get_item_category(_coarse(item))
    if item.color_family not in _RULES.occasion_colors(occasion, slot, [item.color_family]):
        return f"{name}: {item.color_family} is outside the {_label(occasion)} colour policy for {slot}"
    if weather is not None:
        if weather.band == TempBand.HOT and item.warmth == Warmth.HEAVY:
            return f"{name}: too warm for {weather.describe()}"
        if weather.band == TempBand.HOT and item.category == GarmentCategory.OUTERWEAR and not weather.rain:
            return f"{name}: no outerwear needed at {weather.describe()}"
        cold_sensitive = item.category in (
            GarmentCategory.BOTTOMWEAR,
            GarmentCategory.FOOTWEAR,
            GarmentCategory.FULLBODY,
        )
        if weather.band == TempBand.COLD and item.warmth == Warmth.LIGHT and cold_sensitive:
            return f"{name}: too light for {weather.describe()}"
    return None


@cache
def _pair_fault(type_a: str, type_b: str, pattern_a: str, pattern_b: str) -> str | None:
    """'pairing', 'pattern' or None for two garments' raw tags. Cached: it depends on the tags
    alone, and the gap finder asks it ~160k times per closet about the same few values."""
    ta, tb = _clothing_type_of(type_a), _clothing_type_of(type_b)
    if tb not in _RULES.get_paired_items(ta) and ta not in _RULES.get_paired_items(tb):
        return "pairing"
    pa, pb = Pattern(COARSE_PATTERN[PatternName(pattern_a)]), Pattern(COARSE_PATTERN[PatternName(pattern_b)])
    if not (_RULES.is_pattern_compatible(pa, pb) or _RULES.is_pattern_compatible(pb, pa)):
        return "pattern"
    return None


def pair_problem(a: ClosetItem, b: ClosetItem) -> str | None:
    """Why two garments cannot be worn together, or None when they can."""
    fault = _pair_fault(a.garment_type, b.garment_type, a.pattern.value, b.pattern.value)
    if fault == "pairing":
        return f"{a.short_label} + {b.short_label}: not a known pairing"
    if fault == "pattern":
        return f"{a.short_label} + {b.short_label}: two patterns ({a.pattern.value}, {b.pattern.value})"
    return None


def _needs_footwear(occasion: Occasion) -> bool:
    return ClothingType.SHOES in OCCASION_ALLOWED_ITEMS[occasion]


def _is_garment(item: ClosetItem) -> bool:
    return item.category != GarmentCategory.ACCESSORY


def _accessory_context(garments: tuple[ClosetItem, ...], occasion: Occasion) -> AccessoryContext:
    base = garments[0]
    return AccessoryContext(
        base_type=_clothing_type(base),
        base_garment=base.garment_type,
        base_color=base.color_family,
        formality=_target(occasion),
        occasion=occasion,
    )


def _accessory_pairs(items: Iterable[ClosetItem]) -> list[tuple[str, str]]:
    return [(_coarse(i), i.color_family) for i in items]


def violations(outfit: Outfit, occasion: Occasion, weather: Weather | None) -> list[str]:
    """Every rule re-checked on a finished outfit. The engine builds outfits that pass;
    the property tests and ``evaluation/outfit_engine.py`` use this to prove it."""
    problems: list[str] = []
    ids = outfit.item_ids
    if len(set(ids)) != len(ids):
        problems.append("an item is used twice")
    garments = tuple(i for i in outfit.items if _is_garment(i))
    accessories = [i for i in outfit.items if not _is_garment(i)]
    by_cat = {c: [i for i in garments if i.category == c] for c in GarmentCategory}
    one_piece = len(by_cat[GarmentCategory.FULLBODY]) == 1
    two_piece = len(by_cat[GarmentCategory.TOPWEAR]) == 1 and len(by_cat[GarmentCategory.BOTTOMWEAR]) == 1
    if not (one_piece or two_piece) or (one_piece and by_cat[GarmentCategory.BOTTOMWEAR]):
        problems.append("not (top + bottom) or one one-piece")
    if len(by_cat[GarmentCategory.FOOTWEAR]) != (1 if _needs_footwear(occasion) else 0):
        problems.append("wrong footwear count")
    if len(by_cat[GarmentCategory.OUTERWEAR]) > 1 or by_cat[GarmentCategory.OTHER]:
        problems.append("more than one outerwear, or an untyped garment")
    problems += [p for i in outfit.items if (p := item_problem(i, occasion, weather))]
    problems += [p for a, b in combinations(garments, 2) if (p := pair_problem(a, b))]
    if weather is not None and weather.band == TempBand.COLD and not by_cat[GarmentCategory.OUTERWEAR]:
        problems += [
            f"{t.short_label}: too light without a layer"
            for t in by_cat[GarmentCategory.TOPWEAR]
            if t.warmth == Warmth.LIGHT
        ]
    if accessories:
        if len(accessories) > MAX_ACCESSORIES_PER_LOOK:
            problems.append("too many accessories")
        ctx = _accessory_context(garments, occasion)
        allowed = {c.accessory for c in candidates(ctx)}
        problems += [
            f"{a.short_label}: not an accessory for this look"
            for a in accessories
            if as_accessory(a.garment_type) not in allowed
        ]
        problems += [detail for _, detail in coherence_issues(ctx, _accessory_pairs(outfit.items))]
    return problems


# ──────────────────────────────────────────────────────────────────────
#  Building
# ──────────────────────────────────────────────────────────────────────


def _score(
    garments: tuple[ClosetItem, ...],
    occasion: Occasion,
    preferences: Mapping[str, float],
    recently_worn: frozenset[str],
) -> dict[str, float]:
    pairs = list(combinations(garments, 2))
    colour = sum(
        max(_COLOURS.score_pair(_colour(a), _colour(b)), _COLOURS.score_pair(_colour(b), _colour(a))) for a, b in pairs
    ) / max(len(pairs), 1)
    target = _target(occasion)
    formality = 1 - sum(abs(g.formality - target) for g in garments) / len(garments)
    preference = sum(preferences.get(g.id, 0.0) for g in garments) / len(garments)
    recent = -RECENTLY_WORN_PENALTY * sum(g.id in recently_worn for g in garments)
    return {
        "colour_harmony": round(colour, 3),
        "formality_fit": round(formality, 3),
        "preference": round(PREFERENCE_WEIGHT * preference, 3),
        "recently_worn": round(recent, 3),
    }


def _pairs_ok(items: tuple[ClosetItem, ...]) -> bool:
    return all(pair_problem(a, b) is None for a, b in combinations(items, 2))


def _evidence(
    garments: tuple[ClosetItem, ...],
    accessories: list[ClosetItem],
    occasion: Occasion,
    weather: Weather | None,
    recently_worn: frozenset[str],
) -> tuple[str, ...]:
    target = _target(occasion)
    facts = [
        f"Every item is allowed for {_label(occasion)} by the occasion item and colour rules",
        f"{_label(occasion).capitalize()} calls for {_formality(target)} dress; "
        + ", ".join(f"the {g.short_label} is {_formality(g.formality)}" for g in garments),
    ]
    for a, b in combinations(garments, 2):
        score = max(_COLOURS.score_pair(_colour(a), _colour(b)), _COLOURS.score_pair(_colour(b), _colour(a)))
        word = "pairs well" if score >= 0.7 else "pairs acceptably" if score >= 0.5 else "is a neutral pairing"
        facts.append(f"{a.short_label} and {b.short_label}: {word} (colour table {score:.2f})")
    patterned = [g.short_label for g in garments if g.pattern.value != "solid"]
    facts.append(f"Only the {patterned[0]} is patterned" if patterned else "All pieces are solid colours")
    if weather is not None:
        outer = [g.short_label for g in garments if g.category == GarmentCategory.OUTERWEAR]
        line = f"Weather {weather.describe()}: every piece suits it"
        facts.append(line + (f"; the {outer[0]} is the outer layer" if outer else ""))
    facts += [f"The {a.short_label} passes the accessory rules for this look" for a in accessories]
    facts += [f"The {g.short_label} was worn recently (small penalty)" for g in garments if g.id in recently_worn]
    return tuple(facts)


def _attach_accessories(
    garments: tuple[ClosetItem, ...], owned: list[ClosetItem], occasion: Occasion
) -> list[ClosetItem]:
    """Owned accessories in the rules' rank order, kept only while the look stays coherent."""
    if not owned:
        return []
    ctx = _accessory_context(garments, occasion)
    rank = {c.accessory.value: n for n, c in enumerate(candidates(ctx))}
    picked: list[ClosetItem] = []
    for acc in sorted((a for a in owned if a.garment_type in rank), key=lambda a: (rank[a.garment_type], a.id)):
        if len(picked) == MAX_ACCESSORIES_PER_LOOK:
            break
        trial = [*picked, acc]
        if not coherence_issues(ctx, _accessory_pairs((*garments, *trial))):
            picked = trial
    return picked


def _different_enough(a: Outfit, b: Outfit) -> bool:
    ga = {i.id for i in a.items if _is_garment(i)}
    gb = {i.id for i in b.items if _is_garment(i)}
    return max(len(ga - gb), len(gb - ga)) >= MIN_DIFFERENT_GARMENTS


_SLOT_NAMES = {
    GarmentCategory.TOPWEAR: "top",
    GarmentCategory.BOTTOMWEAR: "bottom",
    GarmentCategory.FULLBODY: "one-piece",
    GarmentCategory.FOOTWEAR: "footwear",
}


def _missing(slot: GarmentCategory, closet: list[ClosetItem], occasion: Occasion, weather: Weather | None) -> str:
    owned = [i for i in closet if i.category == slot]
    name = _SLOT_NAMES[slot]
    if not owned:
        return f"no {name} in the closet"
    why = item_problem(owned[0], occasion, weather)
    return f"none of your {len(owned)} {name} item(s) suit {_label(occasion)} (e.g. {why})"


@dataclass(frozen=True)
class Looks:
    """Every valid garment combination (no accessories yet) for one occasion and weather."""

    looks: list[tuple[ClosetItem, ...]]
    slot: dict[GarmentCategory, list[ClosetItem]]
    """The closet's items that pass the item rules, by category."""
    notes: list[str]


def valid_looks(items: list[ClosetItem], occasion: Occasion, weather: Weather | None = None) -> Looks:
    """All garment combinations that pass the item, pair, structure and weather rules.
    ``build_outfits`` scores these; ``engine.gaps`` counts them."""
    ok = [i for i in items if item_problem(i, occasion, weather) is None]
    slot = {c: [i for i in ok if i.category == c] for c in GarmentCategory}
    footwear: list[ClosetItem | None] = list(slot[GarmentCategory.FOOTWEAR]) if _needs_footwear(occasion) else [None]

    bases: list[tuple[ClosetItem, ...]] = []
    for top, bottom in product(slot[GarmentCategory.TOPWEAR], slot[GarmentCategory.BOTTOMWEAR]):
        if pair_problem(top, bottom) is None:
            bases.append((top, bottom))
    for piece in slot[GarmentCategory.FULLBODY]:
        if "topwear" in _RULES.get_outfit_structure(_clothing_type(piece)).get("required", []):
            bases += [(piece, t) for t in slot[GarmentCategory.TOPWEAR] if pair_problem(piece, t) is None]
        else:
            bases.append((piece,))

    looks: list[tuple[ClosetItem, ...]] = []
    for base, shoes in product(bases, footwear):
        core = base if shoes is None else (*base, shoes)
        if shoes is not None and not _pairs_ok(core):
            continue
        looks.append(core)
        for outer in slot[GarmentCategory.OUTERWEAR]:
            look = (*base, outer) if shoes is None else (*base, outer, shoes)
            if _pairs_ok(look):
                looks.append(look)

    notes: list[str] = []
    if weather is not None and weather.band == TempBand.COLD:
        # A light top is fine under a coat, not alone in the cold.
        looks = [
            g
            for g in looks
            if any(i.category == GarmentCategory.OUTERWEAR for i in g)
            or all(i.warmth != Warmth.LIGHT for i in g if i.category == GarmentCategory.TOPWEAR)
        ]
    if weather is not None and weather.wants_outerwear:
        layered = [g for g in looks if any(i.category == GarmentCategory.OUTERWEAR for i in g)]
        if layered:
            looks = layered
        elif looks:
            notes.append(f"{weather.describe()}, but no outerwear in the closet suits {_label(occasion)}")
    return Looks(looks, slot, notes)


def build_outfits(
    closet: list[ClosetItem],
    occasion: Occasion,
    weather: Weather | None = None,
    *,
    preferences: Mapping[str, float] | None = None,
    recently_worn: Iterable[str] = (),
) -> OutfitResult:
    """Up to 3 outfits from *closet* for *occasion*, best first, or the reason there are none."""
    prefs = preferences or {}
    recent = frozenset(recently_worn)
    items = sorted(closet, key=lambda i: i.id)  # same input → same output
    found = valid_looks(items, occasion, weather)
    looks, slot, notes = found.looks, found.slot, found.notes

    if not looks:
        needs = [GarmentCategory.FOOTWEAR] if _needs_footwear(occasion) else []
        two = [c for c in (GarmentCategory.TOPWEAR, GarmentCategory.BOTTOMWEAR, *needs) if not slot[c]]
        one = [c for c in (GarmentCategory.FULLBODY, *needs) if not slot[c]]
        gaps = min(two, one, key=len)
        why = "; ".join(_missing(c, items, occasion, weather) for c in gaps) or (
            f"the pieces that suit {_label(occasion)} do not combine under the style and weather rules"
        )
        return OutfitResult([], reason=f"No outfit for {_label(occasion)}: {why}.", notes=notes)

    accessories = slot[GarmentCategory.ACCESSORY]
    scored: list[Outfit] = []
    for garments in looks:
        parts = _score(garments, occasion, prefs, recent)
        scored.append(Outfit(garments, round(sum(parts.values()), 3), parts, ()))
    scored.sort(key=lambda o: (-o.score, o.item_ids))

    chosen: list[Outfit] = []
    for cand in scored:
        if all(_different_enough(cand, c) for c in chosen):
            chosen.append(cand)
            if len(chosen) == MAX_OUTFITS:
                break

    final = []
    for o in chosen:
        acc = _attach_accessories(o.items, accessories, occasion)
        evidence = _evidence(o.items, acc, occasion, weather, recent)
        final.append(Outfit((*o.items, *acc), o.score, o.score_parts, evidence))

    reason: str | None = None
    if len(final) < MAX_OUTFITS:
        reason = (
            f"Only {len(final)} outfit(s) for {_label(occasion)} differ by at least {MIN_DIFFERENT_GARMENTS} pieces; "
            "more tops, bottoms or shoes that suit it would give more choice."
        )
    return OutfitResult(final, reason=reason, notes=notes)
