"""Accessory Rule Engine — which accessories, in which colours, for which look.

Replaces the single ``"accessory"`` outfit slot. That slot sent the shopping
agent off to search for the literal word; a belt and a clutch are not the same
slot, do not pair with the same outfits, and are not the same query.

Two deterministic stages:

1. **Candidates** — (occasion × formality × shopping intent × base garment) →
   a ranked shortlist of ``AccessoryType`` values.
2. **Coherence** — ``coherence_issues`` checks a look's accessories the way a
   stylist would: at most ``MAX_ACCESSORIES_PER_LOOK``; leather agrees (a belt
   takes the shoes' leather colour); metals agree (one finish per look); one
   statement piece; one per group (neckwear, bag, headwear); a piece's
   prerequisite is in the look (a tie needs a collared shirt, a belt needs belt
   loops). The outfit engine adds owned accessories only while this stays empty.

No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from backend.core.accessory_policy import MAX_ACCESSORIES_PER_LOOK
from backend.schemas.clothing import ClothingType
from backend.schemas.taxonomy import AccessoryType, Formality, Occasion

Material = Literal["leather", "metal", "textile", "other"]
Need = Literal["collared_shirt", "tailoring", "belted_bottom", "ethnic"]
Lean = Literal["any", "menswear", "womenswear"]


@dataclass(frozen=True)
class AccessoryRule:
    formality: tuple[Formality, Formality]
    """Inclusive band of the *look's* formality this piece belongs in."""
    weight: float
    """The stylist's default preference, 0–1. Orders the shortlist when Jev is absent."""
    material: Material
    group: str | None = None
    """At most one accessory per group in a look (neckwear, bag, headwear)."""
    statement: bool = False
    lean: Lean = "any"
    occasions: frozenset[Occasion] = frozenset()
    """When non-empty, the piece is suggested only for these occasions."""
    excluded: frozenset[Occasion] = frozenset()
    needs: Need | None = None


_F = Formality
_O = Occasion

ACCESSORY_RULES: dict[AccessoryType, AccessoryRule] = {
    AccessoryType.WATCH: AccessoryRule((_F.CASUAL, _F.BLACK_TIE), 0.9, "metal", group="wrist"),
    AccessoryType.BELT: AccessoryRule(
        (_F.CASUAL, _F.BLACK_TIE),
        0.85,
        "leather",
        needs="belted_bottom",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.LOUNGEWEAR, _O.BEACH_RESORT}),
    ),
    AccessoryType.TIE: AccessoryRule(
        (_F.BUSINESS_FORMAL, _F.BLACK_TIE), 0.8, "textile", group="neckwear", lean="menswear", needs="collared_shirt"
    ),
    AccessoryType.BOW_TIE: AccessoryRule(
        (_F.BUSINESS_FORMAL, _F.BLACK_TIE),
        0.6,
        "textile",
        group="neckwear",
        statement=True,
        lean="menswear",
        occasions=frozenset({_O.COCKTAIL_SEMI_FORMAL, _O.WEDDING_GUEST}),
        needs="collared_shirt",
    ),
    AccessoryType.POCKET_SQUARE: AccessoryRule(
        (_F.SMART_CASUAL, _F.BLACK_TIE), 0.7, "textile", lean="menswear", needs="tailoring"
    ),
    AccessoryType.CUFFLINKS: AccessoryRule(
        (_F.BUSINESS_FORMAL, _F.BLACK_TIE), 0.55, "metal", lean="menswear", needs="collared_shirt"
    ),
    AccessoryType.SCARF: AccessoryRule(
        (_F.CASUAL, _F.BUSINESS_FORMAL),
        0.5,
        "textile",
        group="neckwear",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.BEACH_RESORT, _O.LOUNGEWEAR, _O.INTERVIEW}),
    ),
    AccessoryType.STOLE: AccessoryRule(
        (_F.SMART_CASUAL, _F.BLACK_TIE),
        0.5,
        "textile",
        group="neckwear",
        occasions=frozenset({_O.WEDDING_GUEST, _O.FESTIVE_ETHNIC, _O.COCKTAIL_SEMI_FORMAL}),
    ),
    AccessoryType.DUPATTA: AccessoryRule(
        (_F.CASUAL, _F.BLACK_TIE), 0.85, "textile", group="neckwear", lean="womenswear", needs="ethnic"
    ),
    AccessoryType.SUNGLASSES: AccessoryRule(
        (_F.CASUAL, _F.SMART_CASUAL),
        0.75,
        "other",
        occasions=frozenset({_O.BEACH_RESORT, _O.TRAVEL_COMMUTE, _O.EVERYDAY_CASUAL, _O.SMART_CASUAL}),
    ),
    AccessoryType.CAP: AccessoryRule(
        (_F.CASUAL, _F.CASUAL),
        0.6,
        "textile",
        group="headwear",
        occasions=frozenset({_O.GYM_ATHLEISURE, _O.EVERYDAY_CASUAL, _O.BEACH_RESORT, _O.TRAVEL_COMMUTE}),
    ),
    AccessoryType.HAT: AccessoryRule(
        (_F.CASUAL, _F.SMART_CASUAL),
        0.45,
        "textile",
        group="headwear",
        statement=True,
        occasions=frozenset({_O.BEACH_RESORT, _O.SMART_CASUAL, _O.TRAVEL_COMMUTE}),
    ),
    AccessoryType.BEANIE: AccessoryRule(
        (_F.CASUAL, _F.CASUAL),
        0.4,
        "textile",
        group="headwear",
        occasions=frozenset({_O.EVERYDAY_CASUAL, _O.TRAVEL_COMMUTE}),
    ),
    AccessoryType.NECKLACE: AccessoryRule(
        (_F.CASUAL, _F.BLACK_TIE),
        0.6,
        "metal",
        statement=True,
        lean="womenswear",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.LOUNGEWEAR, _O.INTERVIEW}),
    ),
    AccessoryType.EARRINGS: AccessoryRule(
        (_F.CASUAL, _F.BLACK_TIE),
        0.65,
        "metal",
        statement=True,
        lean="womenswear",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.LOUNGEWEAR}),
    ),
    AccessoryType.BRACELET: AccessoryRule(
        (_F.CASUAL, _F.SMART_CASUAL),
        0.45,
        "metal",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.LOUNGEWEAR, _O.INTERVIEW, _O.BUSINESS_FORMAL}),
    ),
    AccessoryType.RINGS: AccessoryRule(
        (_F.CASUAL, _F.BLACK_TIE),
        0.35,
        "metal",
        excluded=frozenset({_O.GYM_ATHLEISURE, _O.LOUNGEWEAR}),
    ),
    AccessoryType.BROOCH: AccessoryRule(
        (_F.SMART_CASUAL, _F.BLACK_TIE),
        0.4,
        "metal",
        statement=True,
        occasions=frozenset({_O.WEDDING_GUEST, _O.FESTIVE_ETHNIC, _O.COCKTAIL_SEMI_FORMAL}),
    ),
    AccessoryType.TOTE_BAG: AccessoryRule(
        (_F.CASUAL, _F.SMART_CASUAL),
        0.5,
        "leather",
        group="bag",
        occasions=frozenset({_O.EVERYDAY_CASUAL, _O.TRAVEL_COMMUTE, _O.BEACH_RESORT, _O.BUSINESS_CASUAL}),
    ),
    AccessoryType.BACKPACK: AccessoryRule(
        (_F.CASUAL, _F.CASUAL),
        0.55,
        "other",
        group="bag",
        occasions=frozenset({_O.EVERYDAY_CASUAL, _O.TRAVEL_COMMUTE, _O.GYM_ATHLEISURE}),
    ),
    AccessoryType.CROSSBODY_BAG: AccessoryRule(
        (_F.CASUAL, _F.SMART_CASUAL),
        0.5,
        "leather",
        group="bag",
        occasions=frozenset(
            {_O.EVERYDAY_CASUAL, _O.TRAVEL_COMMUTE, _O.PARTY_NIGHT_OUT, _O.DATE_NIGHT, _O.SMART_CASUAL}
        ),
    ),
    AccessoryType.CLUTCH: AccessoryRule(
        (_F.SMART_CASUAL, _F.BLACK_TIE),
        0.65,
        "metal",
        group="bag",
        lean="womenswear",
        occasions=frozenset(
            {_O.PARTY_NIGHT_OUT, _O.COCKTAIL_SEMI_FORMAL, _O.WEDDING_GUEST, _O.DATE_NIGHT, _O.FESTIVE_ETHNIC}
        ),
    ),
    AccessoryType.BRIEFCASE: AccessoryRule(
        (_F.SMART_CASUAL, _F.BLACK_TIE),
        0.6,
        "leather",
        group="bag",
        occasions=frozenset({_O.BUSINESS_FORMAL, _O.BUSINESS_CASUAL, _O.INTERVIEW}),
    ),
}
"""Every suggestable accessory. ``SOCKS`` is deliberately absent: socks are a
recognisable upload, not a styling move anyone shops a look for."""

OCCASION_FORMALITY: dict[Occasion, Formality] = {
    _O.BUSINESS_FORMAL: _F.BUSINESS_FORMAL,
    _O.INTERVIEW: _F.BUSINESS_FORMAL,
    _O.WEDDING_GUEST: _F.BUSINESS_FORMAL,
    _O.COCKTAIL_SEMI_FORMAL: _F.BUSINESS_FORMAL,
    _O.BUSINESS_CASUAL: _F.SMART_CASUAL,
    _O.SMART_CASUAL: _F.SMART_CASUAL,
    _O.DATE_NIGHT: _F.SMART_CASUAL,
    _O.FESTIVE_ETHNIC: _F.SMART_CASUAL,
    _O.EVERYDAY_CASUAL: _F.CASUAL,
    _O.PARTY_NIGHT_OUT: _F.CASUAL,
    _O.TRAVEL_COMMUTE: _F.CASUAL,
    _O.BEACH_RESORT: _F.CASUAL,
    _O.GYM_ATHLEISURE: _F.CASUAL,
    _O.LOUNGEWEAR: _F.LOUNGE,
}
"""The register a look for this occasion is built in. When the user names an
occasion, this — not the uploaded garment's own formality — sets the band."""

_ETHNIC_GARMENTS = frozenset({"kurta", "salwar_kameez", "anarkali", "lehenga", "saree", "sherwani", "nehru_jacket"})
_DUPATTA_GARMENTS = frozenset({"kurta", "salwar_kameez", "anarkali", "lehenga"})
# Elastic waists and anything worn over the waist (a kurta covers it).
_UNBELTED_GARMENTS = frozenset({"joggers", "track_pants", "leggings", "palazzo", "dhoti", "tunic"}) | _ETHNIC_GARMENTS
_WOMENSWEAR_GARMENTS = frozenset(
    {"blouse", "dress", "skirt", "gown", "saree", "lehenga", "anarkali", "salwar_kameez", "heels", "crop_top"}
)
_MENSWEAR_GARMENTS = frozenset({"sherwani", "dhoti", "nehru_jacket"})

_TAILORING = frozenset({ClothingType.BLAZER.value, ClothingType.SUIT.value})
_BELTED = frozenset(
    {
        ClothingType.TROUSERS.value,
        ClothingType.JEANS.value,
        ClothingType.CHINOS.value,
        ClothingType.SHORTS.value,
        ClothingType.SUIT.value,
    }
)
_SHIRTED = frozenset({ClothingType.SHIRT.value, ClothingType.SUIT.value})

_LEATHER_COLOURS = {"black": "black", "brown": "brown", "beige": "tan", "cream": "tan", "maroon": "brown"}


# Neckwear is not a colour complement: a white tie is costume. These are the
# conventional tie colours, tried in order, skipping any already in the look.
def accessory_name(accessory: AccessoryType | str) -> str:
    value = accessory.value if isinstance(accessory, AccessoryType) else accessory
    return value.replace("_", " ")


def as_accessory(item_type: str) -> AccessoryType | None:
    """The ``AccessoryType`` an outfit item names, or None for garments."""
    normalized = (item_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    member = AccessoryType._value2member_map_.get(normalized)
    return member if isinstance(member, AccessoryType) and member != AccessoryType.OTHER else None


# ──────────────────────────────────────────────────────────────────────
#  Stage 1 — candidates
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AccessoryContext:
    """What the rules need to know about the look being built."""

    base_type: ClothingType
    base_garment: str
    """Fine type ("kurta", "joggers") when known, else the coarse value."""
    base_color: str
    formality: Formality
    occasion: Occasion | None = None
    shopping_intent: str = "unisex"

    @property
    def lean(self) -> Lean:
        """The gender lean to filter by: the shopper's, else the garment's own.

        An explicit menswear/womenswear intent wins. Under ``unisex`` a saree or
        a sherwani still says who the look is for; anything else leaves the
        lean at ``any``, which admits only gender-neutral pieces.
        """
        if self.shopping_intent == "menswear":
            return "menswear"
        if self.shopping_intent == "womenswear":
            return "womenswear"
        if self.base_garment in _WOMENSWEAR_GARMENTS:
            return "womenswear"
        if self.base_garment in _MENSWEAR_GARMENTS:
            return "menswear"
        return "any"


@dataclass(frozen=True)
class AccessoryCandidate:
    accessory: AccessoryType
    score: float
    reason: str


def _rule_allows(rule: AccessoryRule, ctx: AccessoryContext) -> str | None:
    """None when the rule admits this context, else why not (for logs and tests)."""
    low, high = rule.formality
    if not low <= ctx.formality <= high:
        return "formality"
    if rule.lean != "any" and rule.lean != ctx.lean:
        # A gendered piece needs a gendered signal. "unisex" with a neutral
        # garment means the suggestion has to work for anyone.
        return "lean"
    if ctx.occasion is not None:
        if ctx.occasion in rule.excluded:
            return "occasion_excluded"
        if rule.occasions and ctx.occasion not in rule.occasions:
            return "occasion"
    elif rule.occasions and rule.weight < 0.7:
        # No occasion to go on: only the broadly useful occasion-specific
        # pieces (sunglasses, a cap) survive; a brooch needs a reason.
        return "occasion"
    if rule.needs == "ethnic" and ctx.base_garment not in _DUPATTA_GARMENTS:
        return "needs"
    return None


def candidates(ctx: AccessoryContext) -> list[AccessoryCandidate]:
    """The ranked accessory shortlist for a look.

    The rule weight orders it, with a bonus for pieces made for this exact
    occasion.
    """
    if ctx.formality == _F.LOUNGE:
        return []
    if ctx.base_type == ClothingType.ACCESSORY and as_accessory(ctx.base_garment) is None:
        # An accessory upload of unknown kind — nothing safe to coordinate with.
        return []

    out: list[AccessoryCandidate] = []
    base_accessory = as_accessory(ctx.base_garment)
    for accessory, rule in ACCESSORY_RULES.items():
        if accessory == base_accessory or _rule_allows(rule, ctx) is not None:
            continue
        specific = ctx.occasion is not None and ctx.occasion in rule.occasions
        score = min(1.0, rule.weight + (0.15 if specific else 0.0))
        reason = f"suits a {_formality_word(ctx.formality)} look"
        if specific and ctx.occasion is not None:
            reason = f"made for {ctx.occasion.value.replace('_', ' ')}"
        out.append(AccessoryCandidate(accessory, round(score, 3), reason))
    out.sort(key=lambda c: (-c.score, c.accessory.value))
    return out


def _formality_word(level: Formality) -> str:
    return level.name.lower().replace("_", "-")


# ──────────────────────────────────────────────────────────────────────
#  Stage 2 — coherence
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _Look:
    """The garments an accessory has to agree with."""

    ctx: AccessoryContext
    items: list[tuple[str, str]] = field(default_factory=list)
    """(item_type, colour) of the recommended garments, base excluded."""

    @property
    def types(self) -> set[str]:
        return {self.ctx.base_type.value, *(t for t, _ in self.items)}

    def footwear_colour(self) -> str | None:
        if self.ctx.base_type == ClothingType.SHOES:
            return self.ctx.base_color
        return next((c for t, c in self.items if t == ClothingType.SHOES.value), None)


def _need_met(need: Need | None, look: _Look) -> bool:
    if need is None:
        return True
    garment = look.ctx.base_garment
    if need == "collared_shirt":
        return bool(look.types & _SHIRTED) and garment not in _ETHNIC_GARMENTS
    if need == "tailoring":
        return bool(look.types & _TAILORING) or garment == "nehru_jacket"
    if need == "belted_bottom":
        return bool(look.types & _BELTED) and garment not in _UNBELTED_GARMENTS
    return garment in _DUPATTA_GARMENTS


def coherence_issues(ctx: AccessoryContext, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Coordination rules re-checked on a finished look: (offending accessory, detail).

    ``items`` is every recommended item as (item_type, colour), accessories
    included. The rules above construct looks that pass by design; this is the
    verifier's independent check that nothing downstream broke them.
    """
    garments = [(t, c) for t, c in items if as_accessory(t) is None]
    accessories = [(a, c) for t, c in items if (a := as_accessory(t)) is not None]
    look = _Look(ctx, garments)
    issues: list[tuple[str, str]] = []

    if len(accessories) > MAX_ACCESSORIES_PER_LOOK:
        extra = accessories[MAX_ACCESSORIES_PER_LOOK][0].value
        issues.append((extra, f"more than {MAX_ACCESSORIES_PER_LOOK} accessories in one look"))

    metals = {c for a, c in accessories if a in ACCESSORY_RULES and ACCESSORY_RULES[a].material == "metal"}
    if len(metals) > 1:
        last = next(a for a, _ in reversed(accessories) if ACCESSORY_RULES[a].material == "metal")
        issues.append((last.value, f"mixed metal finishes: {', '.join(sorted(metals))}"))

    statements = [a for a, _ in accessories if a in ACCESSORY_RULES and ACCESSORY_RULES[a].statement]
    if len(statements) > 1:
        issues.append((statements[-1].value, "more than one statement piece"))

    seen_groups: set[str] = set()
    for accessory, colour in accessories:
        rule = ACCESSORY_RULES.get(accessory)
        if rule is None:
            continue
        if rule.group is not None:
            if rule.group in seen_groups:
                issues.append((accessory.value, f"two {rule.group} pieces in one look"))
            seen_groups.add(rule.group)
        if not _need_met(rule.needs, look):
            issues.append((accessory.value, f"{accessory_name(accessory)} without its prerequisite ({rule.needs})"))
        if accessory == AccessoryType.BELT:
            shoes = look.footwear_colour()
            expected = _LEATHER_COLOURS.get(shoes or "")
            if expected is not None and colour != expected:
                issues.append((accessory.value, f"{colour} belt with {shoes} shoes — leather should agree"))
    return issues
