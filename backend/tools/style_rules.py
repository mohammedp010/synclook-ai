"""Style Rule Engine Tool — deterministic style, pattern, and item-pairing logic.

Callable utility that agents can invoke for style-related decisions.
No LLM calls — purely rule-based.
"""

from __future__ import annotations

from backend.schemas.clothing import ClothingType, Color, Pattern, Style

# ──────────────────────────────────────────────────────────────────────
#  Item-pairing table
# ──────────────────────────────────────────────────────────────────────

ITEM_PAIRINGS: dict[ClothingType, list[ClothingType]] = {
    # Tops → bottoms + outerwear
    ClothingType.TSHIRT: [ClothingType.JEANS, ClothingType.CHINOS, ClothingType.SHORTS, ClothingType.JACKET, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.SHIRT: [ClothingType.TROUSERS, ClothingType.CHINOS, ClothingType.JEANS, ClothingType.BLAZER, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.BLOUSE: [ClothingType.SKIRT, ClothingType.TROUSERS, ClothingType.JEANS, ClothingType.BLAZER, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.SWEATER: [ClothingType.JEANS, ClothingType.CHINOS, ClothingType.TROUSERS, ClothingType.COAT, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.HOODIE: [ClothingType.JEANS, ClothingType.SHORTS, ClothingType.CHINOS, ClothingType.SHOES, ClothingType.ACCESSORY],
    # Outerwear → tops + bottoms
    ClothingType.JACKET: [ClothingType.TSHIRT, ClothingType.SHIRT, ClothingType.JEANS, ClothingType.CHINOS, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.BLAZER: [ClothingType.SHIRT, ClothingType.BLOUSE, ClothingType.TROUSERS, ClothingType.CHINOS, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.COAT: [ClothingType.SWEATER, ClothingType.SHIRT, ClothingType.TROUSERS, ClothingType.JEANS, ClothingType.SHOES, ClothingType.ACCESSORY],
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
    ClothingType.JEANS: [ClothingType.TSHIRT, ClothingType.SHIRT, ClothingType.JACKET, ClothingType.SWEATER, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.SHORTS: [ClothingType.TSHIRT, ClothingType.SHIRT, ClothingType.HOODIE, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.CHINOS: [ClothingType.SHIRT, ClothingType.TSHIRT, ClothingType.BLAZER, ClothingType.SWEATER, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.SKIRT: [ClothingType.BLOUSE, ClothingType.TSHIRT, ClothingType.SWEATER, ClothingType.JACKET, ClothingType.SHOES, ClothingType.ACCESSORY],
    # Full outfits → accessories/outerwear
    ClothingType.DRESS: [ClothingType.JACKET, ClothingType.BLAZER, ClothingType.COAT, ClothingType.SHOES, ClothingType.ACCESSORY],
    ClothingType.SUIT: [ClothingType.SHIRT, ClothingType.COAT, ClothingType.SHOES, ClothingType.ACCESSORY],
    # Footwear/accessories as base uploads still need enough structure for a look.
    ClothingType.SHOES: [ClothingType.JEANS, ClothingType.TROUSERS, ClothingType.CHINOS, ClothingType.TSHIRT, ClothingType.SHIRT, ClothingType.ACCESSORY],
    ClothingType.ACCESSORY: [ClothingType.JEANS, ClothingType.TROUSERS, ClothingType.CHINOS, ClothingType.TSHIRT, ClothingType.SHIRT, ClothingType.SHOES],
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
INVALID_ITEMS_BY_GENDER: dict[str, set[ClothingType]] = {
    "male": INVALID_ITEMS_BY_SHOPPING_INTENT["menswear"],
    "female": INVALID_ITEMS_BY_SHOPPING_INTENT["womenswear"],
    "unisex": INVALID_ITEMS_BY_SHOPPING_INTENT["unisex"],
    **INVALID_ITEMS_BY_SHOPPING_INTENT,
}

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

SAFE_FALLBACK_BY_BASE_CATEGORY: dict[str, list[ClothingType]] = {
    "bottomwear": [
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.HOODIE,
        ClothingType.SWEATER,
    ],
    "topwear": [
        ClothingType.TROUSERS,
        ClothingType.JEANS,
        ClothingType.CHINOS,
    ],
    "outerwear": [
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.TROUSERS,
    ],
    "footwear": [
        ClothingType.JEANS,
        ClothingType.TROUSERS,
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
    ],
    "accessory": [
        ClothingType.JEANS,
        ClothingType.TROUSERS,
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
    ],
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
    return None

# ──────────────────────────────────────────────────────────────────────
#  Style compatibility table
# ──────────────────────────────────────────────────────────────────────

STYLE_COMPATIBILITY: dict[Style, list[Style]] = {
    Style.FORMAL: [Style.FORMAL, Style.SMART_CASUAL],
    Style.CASUAL: [Style.CASUAL, Style.STREETWEAR, Style.SMART_CASUAL, Style.SPORTY],
    Style.SMART_CASUAL: [Style.SMART_CASUAL, Style.FORMAL, Style.CASUAL],
    Style.STREETWEAR: [Style.STREETWEAR, Style.CASUAL, Style.SPORTY],
    Style.SPORTY: [Style.SPORTY, Style.CASUAL, Style.STREETWEAR],
    Style.BOHEMIAN: [Style.BOHEMIAN, Style.CASUAL],
    Style.MINIMALIST: [Style.MINIMALIST, Style.SMART_CASUAL, Style.FORMAL, Style.CASUAL],
    Style.OTHER: [s for s in Style],
}

STYLE_ALLOWED_ITEMS: dict[Style, set[ClothingType]] = {
    # Streetwear focuses on relaxed tops/bottoms; avoid formal outerwear.
    Style.STREETWEAR: {
        ClothingType.TSHIRT,
        ClothingType.HOODIE,
        ClothingType.SHIRT,
        ClothingType.SWEATER,
        ClothingType.JACKET,
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.TROUSERS,
        ClothingType.SHORTS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    # Formal looks should stay sharp and structured.
    Style.FORMAL: {
        ClothingType.SHIRT,
        ClothingType.BLAZER,
        ClothingType.COAT,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.SUIT,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    # Casual remains flexible but excludes highly occasion-specific pieces.
    Style.CASUAL: {
        ClothingType.TSHIRT,
        ClothingType.SHIRT,
        ClothingType.HOODIE,
        ClothingType.SWEATER,
        ClothingType.JACKET,
        ClothingType.JEANS,
        ClothingType.CHINOS,
        ClothingType.TROUSERS,
        ClothingType.SHORTS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    Style.SMART_CASUAL: {
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.SWEATER,
        ClothingType.BLAZER,
        ClothingType.JACKET,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.JEANS,
        ClothingType.COAT,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    Style.SPORTY: {
        ClothingType.TSHIRT,
        ClothingType.HOODIE,
        ClothingType.SHORTS,
        ClothingType.JACKET,
        ClothingType.JEANS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    Style.BOHEMIAN: {
        ClothingType.SHIRT,
        ClothingType.BLOUSE,
        ClothingType.SWEATER,
        ClothingType.JACKET,
        ClothingType.TROUSERS,
        ClothingType.JEANS,
        ClothingType.SKIRT,
        ClothingType.DRESS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    Style.MINIMALIST: {
        ClothingType.SHIRT,
        ClothingType.TSHIRT,
        ClothingType.SWEATER,
        ClothingType.JACKET,
        ClothingType.BLAZER,
        ClothingType.COAT,
        ClothingType.TROUSERS,
        ClothingType.CHINOS,
        ClothingType.JEANS,
        ClothingType.SHOES,
        ClothingType.ACCESSORY,
    },
    Style.OTHER: set(ClothingType),
}

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

    def get_safe_fallback_items(
        self,
        base_item_type: ClothingType | str,
        *,
        detected_style: Style,
        gender: str = "unisex",
    ) -> list[ClothingType]:
        """Return conservative fallback items for low-confidence detections."""
        category = self.get_item_category(base_item_type)
        candidates = SAFE_FALLBACK_BY_BASE_CATEGORY.get(category, [ClothingType.SHIRT, ClothingType.TROUSERS])
        return [
            item
            for item in candidates
            if self.is_item_allowed_for_gender(item, gender)
            and self.is_item_allowed_for_style(detected_style, item)
        ]

    # ── Style compatibility ──────────────────────────────────────────

    def get_compatible_styles(self, style: Style) -> list[Style]:
        """Return styles compatible with *style*, ordered best-first."""
        return list(STYLE_COMPATIBILITY.get(style, [style]))

    def is_style_compatible(self, style_a: Style, style_b: Style) -> bool:
        """Check whether two styles can be mixed in one outfit."""
        compatible = STYLE_COMPATIBILITY.get(style_a, [])
        return style_b in compatible

    def is_item_allowed_for_style(self, detected_style: Style, item_type: ClothingType | str) -> bool:
        """Check if an item type is valid under the detected style context."""
        ct = _to_clothing_type(item_type)
        if ct is None:
            return False
        allowed = STYLE_ALLOWED_ITEMS.get(detected_style, set(ClothingType))
        return ct in allowed

    # ── Pattern pairing ──────────────────────────────────────────────

    def get_paired_patterns(self, pattern: Pattern) -> list[Pattern]:
        """Return patterns that pair well with *pattern*."""
        return list(PATTERN_PAIRS.get(pattern, [Pattern.SOLID]))

    def is_pattern_compatible(self, pattern_a: Pattern, pattern_b: Pattern) -> bool:
        """Check whether two patterns can be mixed in one outfit."""
        pairs = PATTERN_PAIRS.get(pattern_a, [])
        return pattern_b in pairs

    # ── Composite scoring ────────────────────────────────────────────

    def compute_match_score(
        self,
        detected_style: Style,
        suggested_style: Style,
        detected_pattern: Pattern,
    ) -> float:
        """Score 0-1 for how well a suggested item fits the detected garment.

        Considers style compatibility and pattern ease-of-pairing.
        """
        score = 0.5  # base

        if suggested_style in STYLE_COMPATIBILITY.get(detected_style, []):
            score += 0.25
        if suggested_style == detected_style:
            score += 0.1

        # Solid patterns pair with everything — bonus
        if detected_pattern == Pattern.SOLID:
            score += 0.1

        return min(round(score, 2), 1.0)
