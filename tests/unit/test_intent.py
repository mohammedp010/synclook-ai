"""Tests for the StyleIntent schema (the request parser's output)."""

from __future__ import annotations

from backend.schemas.clothing import Style
from backend.schemas.intent import StyleIntent
from backend.schemas.taxonomy import Occasion


class TestStyleIntentNormalization:
    def test_negative_budget_dropped(self) -> None:
        intent = StyleIntent(budget_total_inr=-100).normalized()
        assert intent.budget_total_inr is None

    def test_lists_are_deduped_lowercased_capped(self) -> None:
        intent = StyleIntent(avoid_items=["  Blazer ", "blazer", "SKIRT"] + [f"item{i}" for i in range(20)])
        normalized = intent.normalized()
        assert normalized.avoid_items[:2] == ["blazer", "skirt"]
        assert len(normalized.avoid_items) <= 8

    def test_preferred_styles_capped_and_deduped(self) -> None:
        intent = StyleIntent(preferred_styles=[Style.FORMAL, Style.FORMAL, Style.CASUAL, Style.SPORTY, Style.BOHEMIAN])
        assert intent.normalized().preferred_styles == [Style.FORMAL, Style.CASUAL, Style.SPORTY]

    def test_is_empty(self) -> None:
        assert StyleIntent().is_empty
        assert not StyleIntent(occasion="wedding").is_empty
        assert not StyleIntent(occasion_type=Occasion.WEDDING_GUEST).is_empty

    def test_typed_occasion_is_in_the_extraction_schema(self) -> None:
        # One call fills the words and the type.
        assert "occasion_type" in StyleIntent.model_json_schema()["properties"]
        assert StyleIntent(occasion_type=Occasion.BEACH_RESORT).normalized().occasion_type is Occasion.BEACH_RESORT

    def test_an_invented_occasion_becomes_none_not_an_error(self) -> None:
        assert StyleIntent.model_validate({"occasion_type": "volcano_party"}).occasion_type is None
        assert StyleIntent.model_validate({"occasion_type": "wedding_guest"}).occasion_type is Occasion.WEDDING_GUEST
