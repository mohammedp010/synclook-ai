"""Unit tests for StyleRuleEngineTool."""

from backend.schemas.clothing import ClothingType, Pattern
from backend.schemas.taxonomy import Occasion
from backend.tools.style_rules import (
    ITEM_PAIRINGS,
    OCCASION_ALLOWED_ITEMS,
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

    # ── pattern compatibility ────────────────────────────────────────

    def test_is_pattern_compatible_solid_with_striped(self) -> None:
        assert self.tool.is_pattern_compatible(Pattern.SOLID, Pattern.STRIPED)

    def test_striped_not_compatible_with_floral(self) -> None:
        assert not self.tool.is_pattern_compatible(Pattern.STRIPED, Pattern.FLORAL)


class TestOccasionRules:
    """Phase 5: a named occasion owns the item gate and the colour policy."""

    def setup_method(self) -> None:
        self.tool = StyleRuleEngineTool()

    def test_every_occasion_has_items(self) -> None:
        for occasion in Occasion:
            assert OCCASION_ALLOWED_ITEMS[occasion]

    def test_occasion_gate_fixes_what_the_style_route_got_wrong(self) -> None:
        # Each of these was a judged-adherence miss under occasion → Style.
        assert not self.tool.is_item_allowed_for_occasion(Occasion.BUSINESS_FORMAL, ClothingType.CHINOS)
        assert not self.tool.is_item_allowed_for_occasion(Occasion.GYM_ATHLEISURE, ClothingType.TROUSERS)
        assert not self.tool.is_item_allowed_for_occasion(Occasion.BEACH_RESORT, ClothingType.BLAZER)
        assert not self.tool.is_item_allowed_for_occasion(Occasion.FESTIVE_ETHNIC, ClothingType.SHORTS)
        assert not self.tool.is_item_allowed_for_occasion(Occasion.LOUNGEWEAR, ClothingType.SHOES)

    def test_formal_footwear_is_black_or_brown(self) -> None:
        colours = self.tool.occasion_colors(Occasion.INTERVIEW, "footwear", ["white", "grey", "brown"])
        assert colours == ["brown"]
        # Nothing proposed survives → the policy's palette stands in.
        assert self.tool.occasion_colors(Occasion.INTERVIEW, "footwear", ["white", "red"]) == ["black", "brown"]

    def test_no_white_look_at_a_wedding_but_a_white_shirt_is_fine(self) -> None:
        assert "white" not in self.tool.occasion_colors(Occasion.WEDDING_GUEST, "bottomwear", ["white", "navy"])
        assert "cream" not in self.tool.occasion_colors(Occasion.FESTIVE_ETHNIC, "outerwear", ["cream", "maroon"])
        assert self.tool.occasion_colors(Occasion.WEDDING_GUEST, "topwear", ["white", "navy"]) == ["white", "navy"]

    def test_casual_occasions_leave_colour_to_the_colour_rules(self) -> None:
        proposed = ["red", "white", "yellow"]
        assert self.tool.occasion_colors(Occasion.BEACH_RESORT, "bottomwear", proposed) == proposed
