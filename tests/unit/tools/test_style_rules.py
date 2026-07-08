"""Unit tests for StyleRuleEngineTool."""

from backend.schemas.clothing import ClothingType, Pattern, Style
from backend.tools.style_rules import (
    ITEM_PAIRINGS,
    StyleRuleEngineTool,
)


class TestStyleRuleEngineTool:
    """Tests for the deterministic style rule engine."""

    def setup_method(self) -> None:
        self.tool = StyleRuleEngineTool()

    # ── get_paired_items ─────────────────────────────────────────────

    def test_paired_items_returns_list(self) -> None:
        result = self.tool.get_paired_items(ClothingType.SHIRT)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_paired_items_matches_table(self) -> None:
        for ct in ClothingType:
            result = self.tool.get_paired_items(ct)
            expected = ITEM_PAIRINGS.get(ct, [ClothingType.JEANS, ClothingType.TSHIRT])
            assert result == expected

    def test_shirt_pairs_with_trousers(self) -> None:
        result = self.tool.get_paired_items(ClothingType.SHIRT)
        assert ClothingType.TROUSERS in result

    def test_tshirt_pairs_with_jeans(self) -> None:
        result = self.tool.get_paired_items(ClothingType.TSHIRT)
        assert ClothingType.JEANS in result

    def test_trousers_include_streetwear_tops(self) -> None:
        result = self.tool.get_paired_items(ClothingType.TROUSERS, gender="male")
        assert ClothingType.TSHIRT in result
        assert ClothingType.HOODIE in result

    def test_gender_filter_removes_invalid_items(self) -> None:
        result = self.tool.get_paired_items(ClothingType.TROUSERS, gender="male")
        assert ClothingType.BLOUSE not in result
        assert ClothingType.SHIRT in result

    def test_menswear_intent_removes_invalid_items(self) -> None:
        result = self.tool.get_paired_items(ClothingType.TROUSERS, gender="menswear")
        assert ClothingType.BLOUSE not in result
        assert ClothingType.SHIRT in result

    def test_all_intent_keeps_broad_items(self) -> None:
        result = self.tool.get_paired_items(ClothingType.TROUSERS, gender="all")
        assert ClothingType.BLOUSE in result

    def test_get_item_category(self) -> None:
        assert self.tool.get_item_category(ClothingType.TROUSERS) == "bottomwear"
        assert self.tool.get_item_category(ClothingType.BLAZER) == "outerwear"
        assert self.tool.get_item_category(ClothingType.SHOES) == "footwear"
        assert self.tool.get_item_category(ClothingType.ACCESSORY) == "accessory"

    def test_topwear_structure_supports_complete_look_categories(self) -> None:
        structure = self.tool.get_outfit_structure(ClothingType.SHIRT)
        assert structure["required"] == ["bottomwear"]
        assert "footwear" in structure["optional"]
        assert "accessory" in structure["optional"]

    def test_bottomwear_structure_supports_complete_look_categories(self) -> None:
        structure = self.tool.get_outfit_structure(ClothingType.TROUSERS)
        assert structure["required"] == ["topwear"]
        assert "footwear" in structure["optional"]
        assert "accessory" in structure["optional"]

    def test_dress_uses_item_specific_outfit_structure(self) -> None:
        structure = self.tool.get_outfit_structure(ClothingType.DRESS)
        assert structure["required"] == []
        assert structure["optional"] == ["outerwear", "footwear", "accessory"]

    def test_suit_uses_item_specific_outfit_structure(self) -> None:
        structure = self.tool.get_outfit_structure(ClothingType.SUIT)
        assert structure["required"] == ["topwear"]
        assert structure["optional"] == ["outerwear", "footwear", "accessory"]

    def test_safe_fallback_items_for_bottomwear(self) -> None:
        result = self.tool.get_safe_fallback_items(
            ClothingType.TROUSERS,
            detected_style=Style.STREETWEAR,
            gender="male",
        )
        assert ClothingType.BLOUSE not in result
        assert ClothingType.TSHIRT in result

    # ── style compatibility ──────────────────────────────────────────

    def test_compatible_styles_returns_list(self) -> None:
        result = self.tool.get_compatible_styles(Style.FORMAL)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_same_style_always_compatible(self) -> None:
        for style in Style:
            assert self.tool.is_style_compatible(style, style)

    def test_formal_not_compatible_with_streetwear(self) -> None:
        assert not self.tool.is_style_compatible(Style.FORMAL, Style.STREETWEAR)

    def test_casual_compatible_with_streetwear(self) -> None:
        assert self.tool.is_style_compatible(Style.CASUAL, Style.STREETWEAR)

    def test_smart_casual_compatible_with_formal(self) -> None:
        assert self.tool.is_style_compatible(Style.SMART_CASUAL, Style.FORMAL)

    def test_streetwear_disallows_blazer(self) -> None:
        assert not self.tool.is_item_allowed_for_style(Style.STREETWEAR, ClothingType.BLAZER)

    def test_formal_allows_blazer(self) -> None:
        assert self.tool.is_item_allowed_for_style(Style.FORMAL, ClothingType.BLAZER)

    def test_styles_allow_footwear_and_accessories(self) -> None:
        for style in Style:
            assert self.tool.is_item_allowed_for_style(style, ClothingType.SHOES)
            assert self.tool.is_item_allowed_for_style(style, ClothingType.ACCESSORY)

    # ── pattern compatibility ────────────────────────────────────────

    def test_paired_patterns_returns_list(self) -> None:
        result = self.tool.get_paired_patterns(Pattern.SOLID)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_solid_pairs_with_everything(self) -> None:
        # Solid should have the most pattern pairings
        solid_pairs = self.tool.get_paired_patterns(Pattern.SOLID)
        assert len(solid_pairs) >= 3

    def test_striped_pairs_only_with_solid(self) -> None:
        result = self.tool.get_paired_patterns(Pattern.STRIPED)
        assert result == [Pattern.SOLID]

    def test_is_pattern_compatible_solid_with_striped(self) -> None:
        assert self.tool.is_pattern_compatible(Pattern.SOLID, Pattern.STRIPED)

    def test_striped_not_compatible_with_floral(self) -> None:
        assert not self.tool.is_pattern_compatible(Pattern.STRIPED, Pattern.FLORAL)

    # ── compute_match_score ──────────────────────────────────────────

    def test_score_always_between_0_and_1(self) -> None:
        for style in Style:
            for pattern in Pattern:
                score = self.tool.compute_match_score(style, style, pattern)
                assert 0.0 <= score <= 1.0

    def test_same_style_solid_pattern_gets_high_score(self) -> None:
        score = self.tool.compute_match_score(Style.CASUAL, Style.CASUAL, Pattern.SOLID)
        # base 0.5 + compatible 0.25 + same 0.1 + solid 0.1 = 0.95
        assert score == 0.95

    def test_compatible_style_gets_bonus(self) -> None:
        score_compatible = self.tool.compute_match_score(Style.CASUAL, Style.STREETWEAR, Pattern.SOLID)
        score_incompatible = self.tool.compute_match_score(Style.FORMAL, Style.STREETWEAR, Pattern.SOLID)
        assert score_compatible > score_incompatible

    def test_solid_pattern_gives_bonus(self) -> None:
        score_solid = self.tool.compute_match_score(Style.CASUAL, Style.CASUAL, Pattern.SOLID)
        score_striped = self.tool.compute_match_score(Style.CASUAL, Style.CASUAL, Pattern.STRIPED)
        assert score_solid > score_striped
