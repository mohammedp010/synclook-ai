"""Style Rule Engine Tool — deterministic style, pattern, and item-pairing logic.

Callable utility that agents can invoke for style-related decisions.
No LLM calls — purely rule-based.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.schemas.clothing import ClothingType, Pattern
from backend.schemas.taxonomy import AccessoryType, Formality, Occasion
from backend.tools.accessory_rules import OCCASION_FORMALITY

# ──────────────────────────────────────────────────────────────────────
#  Item-pairing table
# ──────────────────────────────────────────────────────────────────────

ITEM_PAIRINGS: dict[ClothingType, list[ClothingType]] = {
    # Tops → bottoms + outerwear
    ClothingType.TSHIRT: [
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.SHORTS,
        ClothingType.JACKET,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.SHIRT: [
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.JEANS,
        ClothingType.BLAZER,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.BLOUSE: [
        ClothingType.SKIRT,
        ClothingType.TROUSERS,
        ClothingType.JEANS,
        ClothingType.BLAZER,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.SWEATER: [
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.TROUSERS,
        ClothingType.COAT,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.HOODIE: [
        ClothingType.JEANS,
        ClothingType.SHORTS,
        ClothingType.CHINOS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    # Outerwear → tops + bottoms
    ClothingType.JACKET: [
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.SWEATER,
        ClothingType.HOODIE,
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.TROUSERS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    # A blazer over a tee, or with jeans, is the taxonomy's own example of smart casual.
    ClothingType.BLAZER: [
        ClothingType.SHIRT,
        ClothingType.BLOUSE,
        ClothingType.TSHIRT,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.JEANS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.COAT: [
        ClothingType.SWEATER,
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.BLOUSE,
        ClothingType.TROUSERS,
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.SKIRT,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    # Bottoms → tops + outerwear
    ClothingType.TROUSERS: [
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.HOODIE,
        ClothingType.SWEATER,
        ClothingType.BLAZER,
        ClothingType.BLOUSE,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.JEANS: [
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.JACKET,
        ClothingType.SWEATER,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.SHORTS: [
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.HOODIE,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.CHINOS: [
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.BLAZER,
        ClothingType.SWEATER,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.SKIRT: [
        ClothingType.BLOUSE,
        ClothingType.TSHIRT,
        ClothingType.SWEATER,
        ClothingType.JACKET,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    # Full outfits → accessories/outerwear
    ClothingType.DRESS: [
        ClothingType.JACKET,
        ClothingType.BLAZER,
        ClothingType.COAT,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    ],
    ClothingType.SUIT: [ClothingType.SHIRT, ClothingType.COAT, ClothingType.SHOES, ClothingType.ACCESSORY],
    # Footwear/accessories as base uploads still need enough structure for a look.
    ClothingType.SHOES: [
        ClothingType.JEANS,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.ACCESSORY,
    ],
    ClothingType.ACCESSORY: [
        ClothingType.JEANS,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.SHOES,
    ],
    ClothingType.OTHER: [ClothingType.JEANS, ClothingType.TSHIRT, ClothingType.SHOES],
}

# ──────────────────────────────────────────────────────────────────────
#  Clothing taxonomy + shopping-intent constraints
# ──────────────────────────────────────────────────────────────────────

CLOTHING_TYPE_CATEGORIES: dict[ClothingType, str] = {
    ClothingType.TSHIRT: "topwear",
    ClothingType.SHIRT: "topwear",
    ClothingType.BLOUSE: "topwear",
    ClothingType.SWEATER: "topwear",
    ClothingType.HOODIE: "topwear",
    ClothingType.JACKET: "outerwear",
    ClothingType.BLAZER: "outerwear",
    ClothingType.COAT: "outerwear",
    ClothingType.TROUSERS: "bottomwear",
    ClothingType.JEANS: "bottomwear",
    ClothingType.SHORTS: "bottomwear",
    ClothingType.CHINOS: "bottomwear",
    ClothingType.SKIRT: "bottomwear",
    ClothingType.DRESS: "topwear",
    ClothingType.SUIT: "topwear",
    ClothingType.SHOES: "footwear",
    ClothingType.ACCESSORY: "accessory",
    ClothingType.OTHER: "topwear",
}

INVALID_ITEMS_BY_SHOPPING_INTENT: dict[str, set[ClothingType]] = {
    "menswear": {ClothingType.BLOUSE, ClothingType.DRESS, ClothingType.SKIRT},
    "womenswear": set(),
    "unisex": set(),
    "all": set(),
}

# Backward-compatible alias for older tests/imports and API terminology.
OUTFIT_STRUCTURE: dict[str, dict[str, list[str]]] = {
    "bottomwear": {
        "required": ["topwear"],
        "optional": ["outerwear", "footwear", "accessory"],
    },
    "topwear": {
        "required": ["bottomwear"],
        "optional": ["outerwear", "footwear", "accessory"],
    },
    "outerwear": {
        "required": ["topwear", "bottomwear"],
        "optional": ["footwear", "accessory"],
    },
    "footwear": {
        "required": ["bottomwear", "topwear"],
        "optional": ["accessory"],
    },
    "accessory": {
        "required": ["topwear", "bottomwear"],
        "optional": ["footwear"],
    },
}

# Item-level structure overrides to handle full-outfit garments.
ITEM_SPECIFIC_OUTFIT_STRUCTURE: dict[ClothingType, dict[str, list[str]]] = {
    # Dresses are already complete base garments; outerwear is optional layering.
    ClothingType.DRESS: {
        "required": [],
        "optional": ["outerwear", "footwear", "accessory"],
    },
    # Suits can be paired with a shirt and optionally additional outerwear.
    ClothingType.SUIT: {
        "required": ["topwear"],
        "optional": ["outerwear", "footwear", "accessory"],
    },
}


def normalize_shopping_intent(value: str | None) -> str:
    """Normalize legacy gender values and new shopping-intent values."""
    intent = (value or "unisex").strip().lower()
    legacy_map = {
        "male": "menswear",
        "men": "menswear",
        "mens": "menswear",
        "female": "womenswear",
        "women": "womenswear",
        "womens": "womenswear",
    }
    intent = legacy_map.get(intent, intent)
    if intent not in INVALID_ITEMS_BY_SHOPPING_INTENT:
        return "unisex"
    return intent


def _to_clothing_type(item_type: ClothingType | str) -> ClothingType | None:
    if isinstance(item_type, ClothingType):
        return item_type
    normalized = (item_type or "").strip().lower().replace("_", "-")
    for ct in ClothingType:
        if ct.value == normalized:
            return ct
    # A concrete accessory ("belt", "pocket_square") is an accessory-slot item:
    # same category, same style and shopping-intent policy as the old bucket.
    if normalized.replace("-", "_") in AccessoryType._value2member_map_:
        return ClothingType.ACCESSORY
    return None


# ──────────────────────────────────────────────────────────────────────
#  Occasion rules (Phase 5)
# ──────────────────────────────────────────────────────────────────────
#
# When the user names an occasion, it — not the garment's style — decides what
# the look may contain. These replace the old route, which mapped the occasion
# onto a ``Style`` and let STYLE_ALLOWED_ITEMS decide: that put chinos at a
# board meeting (``formal`` allows chinos), dress trousers at the gym
# (``sporty`` allows trousers), and had no style at all for a beach or Diwali.

_T = ClothingType
_O = Occasion
_F = Formality

_TAILORED = frozenset({_T.SHIRT, _T.BLOUSE, _T.BLAZER, _T.COAT, _T.TROUSERS, _T.SUIT, _T.SKIRT, _T.DRESS})
_SMART = _TAILORED | {_T.TSHIRT, _T.SWEATER, _T.JACKET, _T.CHINOS, _T.JEANS}
_EVERYDAY = frozenset(
    {
        _T.TSHIRT,
        _T.SHIRT,
        _T.BLOUSE,
        _T.SWEATER,
        _T.HOODIE,
        _T.JACKET,
        _T.COAT,
        _T.TROUSERS,
        _T.JEANS,
        _T.CHINOS,
        _T.SHORTS,
        _T.SKIRT,
        _T.DRESS,
    }
)
_DRESSED = frozenset({_T.SHOES, _T.ACCESSORY})

OCCASION_ALLOWED_ITEMS: dict[Occasion, frozenset[ClothingType]] = {
    _O.BUSINESS_FORMAL: _TAILORED | _DRESSED,
    _O.INTERVIEW: _TAILORED | _DRESSED,
    _O.WEDDING_GUEST: _TAILORED | _DRESSED,
    _O.COCKTAIL_SEMI_FORMAL: _TAILORED | _DRESSED,
    # Festive ethnic wear (kurta, sherwani, lehenga) has no live ClothingType,
    # so the closest the look can get is dressed and tailored — never a tee.
    _O.FESTIVE_ETHNIC: _TAILORED | _DRESSED,
    _O.BUSINESS_CASUAL: _TAILORED | {_T.SWEATER, _T.CHINOS} | _DRESSED,
    _O.SMART_CASUAL: _SMART | _DRESSED,
    _O.DATE_NIGHT: _SMART | _DRESSED,
    _O.PARTY_NIGHT_OUT: (_SMART - {_T.COAT, _T.SWEATER}) | _DRESSED,
    _O.EVERYDAY_CASUAL: _EVERYDAY | _DRESSED,
    _O.TRAVEL_COMMUTE: (_EVERYDAY - {_T.SHORTS}) | _DRESSED,
    _O.BEACH_RESORT: frozenset({_T.TSHIRT, _T.SHIRT, _T.BLOUSE, _T.SHORTS, _T.CHINOS, _T.SKIRT, _T.DRESS}) | _DRESSED,
    _O.GYM_ATHLEISURE: frozenset({_T.TSHIRT, _T.HOODIE, _T.JACKET, _T.SHORTS}) | _DRESSED,
    # At home: no outerwear, no shoes. Accessories are already out of band
    # (``OCCASION_FORMALITY`` puts lounge below every accessory's range).
    _O.LOUNGEWEAR: frozenset({_T.TSHIRT, _T.HOODIE, _T.SWEATER, _T.SHORTS, _T.ACCESSORY}),
}


@dataclass(frozen=True)
class ColorPolicy:
    palettes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Category → the only colours allowed there, in preference order."""
    avoid: frozenset[str] = frozenset()
    avoid_categories: frozenset[str] = frozenset()
    """Where ``avoid`` applies. Empty means everywhere."""


_DARK_NEUTRALS = ("navy", "grey", "black", "beige")
_FORMAL_COLORS = ColorPolicy(
    palettes={
        "footwear": ("black", "brown"),
        "bottomwear": _DARK_NEUTRALS,
        "outerwear": (*_DARK_NEUTRALS, "brown"),
    }
)
# Guests do not wear white to a wedding (and in India white is a mourning
# colour). Shirts are exempt: a white shirt under a jacket is the norm, and the
# judge's objection was an all-white *look*, not a white collar.
_CELEBRATION_AVOID = frozenset({"white", "cream"})
_NOT_TOPWEAR = frozenset({"bottomwear", "outerwear", "footwear"})

FORMALITY_COLOR_POLICY: dict[Formality, ColorPolicy] = {
    _F.BUSINESS_FORMAL: _FORMAL_COLORS,
    _F.BLACK_TIE: _FORMAL_COLORS,
}

OCCASION_COLOR_POLICY: dict[Occasion, ColorPolicy] = {
    _O.WEDDING_GUEST: ColorPolicy(_FORMAL_COLORS.palettes, _CELEBRATION_AVOID, _NOT_TOPWEAR),
    _O.FESTIVE_ETHNIC: ColorPolicy(avoid=_CELEBRATION_AVOID, avoid_categories=_NOT_TOPWEAR),
}
"""Overrides FORMALITY_COLOR_POLICY for the occasion. Keyed on (occasion ×
formality): the register sets the palette, the occasion adds its conventions."""

# ──────────────────────────────────────────────────────────────────────
#  Pattern pairing table
# ──────────────────────────────────────────────────────────────────────

PATTERN_PAIRS: dict[Pattern, list[Pattern]] = {
    Pattern.SOLID: [Pattern.SOLID, Pattern.STRIPED, Pattern.CHECKERED, Pattern.POLKA_DOT, Pattern.PLAID],
    Pattern.STRIPED: [Pattern.SOLID],
    Pattern.CHECKERED: [Pattern.SOLID],
    Pattern.FLORAL: [Pattern.SOLID],
    Pattern.POLKA_DOT: [Pattern.SOLID],
    Pattern.PLAID: [Pattern.SOLID],
    Pattern.ABSTRACT: [Pattern.SOLID],
    Pattern.OTHER: [Pattern.SOLID],
}


class StyleRuleEngineTool:
    """Rule-based styling engine tool.

    Provides methods for item pairing lookups, style/pattern compatibility
    checks, and composite match scoring.  Designed to be called by agents.
    """

    # ── Item pairing ─────────────────────────────────────────────────

    def get_paired_items(self, clothing_type: ClothingType, *, gender: str = "unisex") -> list[ClothingType]:
        """Return clothing types that pair well with *clothing_type*.

        Filtering uses shopping intent. The ``gender`` parameter name is kept
        for backwards compatibility with older call sites.
        """
        pairs = list(ITEM_PAIRINGS.get(clothing_type, [ClothingType.JEANS, ClothingType.TSHIRT]))
        return [item for item in pairs if self.is_item_allowed_for_gender(item, gender)]

    def get_item_category(self, item_type: ClothingType | str) -> str:
        """Return taxonomy category for an item type.

        Current categories: ``topwear``, ``bottomwear``, ``outerwear``,
        ``footwear``, and ``accessory``.
        """
        ct = _to_clothing_type(item_type)
        if ct is None:
            return "topwear"
        return CLOTHING_TYPE_CATEGORIES.get(ct, "topwear")

    def get_outfit_structure(self, base_item_type: ClothingType | str) -> dict[str, list[str]]:
        """Return required/optional category structure for a base garment."""
        ct = _to_clothing_type(base_item_type)
        if ct is not None and ct in ITEM_SPECIFIC_OUTFIT_STRUCTURE:
            return ITEM_SPECIFIC_OUTFIT_STRUCTURE[ct]

        category = self.get_item_category(base_item_type)
        return OUTFIT_STRUCTURE.get(
            category,
            {"required": ["topwear"], "optional": ["outerwear"]},
        )

    def is_item_allowed_for_gender(self, item_type: ClothingType | str, gender: str) -> bool:
        """Check deterministic shopping-intent validity for an item."""
        ct = _to_clothing_type(item_type)
        if ct is None:
            return True
        shopping_intent = normalize_shopping_intent(gender)
        invalid = INVALID_ITEMS_BY_SHOPPING_INTENT.get(shopping_intent, set())
        return ct not in invalid

    # ── Occasion (Phase 5) ───────────────────────────────────────────

    def is_item_allowed_for_occasion(self, occasion: Occasion, item_type: ClothingType | str) -> bool:
        ct = _to_clothing_type(item_type)
        return ct is not None and ct in OCCASION_ALLOWED_ITEMS[occasion]

    def occasion_colors(self, occasion: Occasion, category: str, proposed: list[str]) -> list[str]:
        """Filter a slot's proposed colours through the occasion's colour policy.

        Keeps the colour rules' order where it can. When nothing proposed
        survives, the policy's own palette stands in — a formal look gets black
        shoes rather than no shoes.
        """
        policy = OCCASION_COLOR_POLICY.get(occasion) or FORMALITY_COLOR_POLICY.get(OCCASION_FORMALITY[occasion])
        if policy is None:
            return proposed
        avoid = policy.avoid if not policy.avoid_categories or category in policy.avoid_categories else frozenset()
        palette = policy.palettes.get(category)
        kept = [c for c in proposed if c not in avoid and (palette is None or c in palette)]
        if kept:
            return kept
        return [c for c in palette if c not in avoid] if palette else proposed

    # ── Pattern pairing ──────────────────────────────────────────────

    def is_pattern_compatible(self, pattern_a: Pattern, pattern_b: Pattern) -> bool:
        """Check whether two patterns can be mixed in one outfit."""
        pairs = PATTERN_PAIRS.get(pattern_a, [])
        return pattern_b in pairs
