"""Unit tests for ColorMatcherTool."""

from backend.schemas.clothing import Color
from backend.tools.color_matcher import COLOR_COMPLEMENTS, ColorMatcherTool


class TestColorMatcherTool:
    """Tests for the deterministic color matching tool."""

    def setup_method(self) -> None:
        self.tool = ColorMatcherTool()

    # ── score_pair ───────────────────────────────────────────────────

    def test_same_color_score(self) -> None:
        score = self.tool.score_pair(Color.NAVY, Color.NAVY)
        assert score == 0.6

    def test_best_complement_gets_highest_score(self) -> None:
        # First complement should score 1.0
        best = COLOR_COMPLEMENTS[Color.NAVY][0]
        score = self.tool.score_pair(Color.NAVY, best)
        assert score == 1.0

    def test_later_complement_gets_lower_score(self) -> None:
        complements = COLOR_COMPLEMENTS[Color.BLACK]
        if len(complements) >= 3:
            score_first = self.tool.score_pair(Color.BLACK, complements[0])
            score_third = self.tool.score_pair(Color.BLACK, complements[2])
            assert score_first > score_third

    def test_neutral_non_complement_gets_baseline(self) -> None:
        # GREY is a neutral but not in YELLOW's complement list? Let's check
        # Actually GREY *is* in YELLOW's list, so pick a case where it's not
        # Use a non-complement neutral
        score = self.tool.score_pair(Color.TEAL, Color.BLACK)
        # BLACK is not in TEAL's complement list → neutral baseline 0.4
        assert score == 0.4

    def test_poor_match_score(self) -> None:
        # ORANGE is not in TEAL's complement list and not a neutral
        score = self.tool.score_pair(Color.TEAL, Color.ORANGE)
        assert score == 0.2

    def test_score_always_between_0_and_1(self) -> None:
        for base in Color:
            for candidate in Color:
                score = self.tool.score_pair(base, candidate)
                assert 0.0 <= score <= 1.0
