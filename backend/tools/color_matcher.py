"""Color Matching Tool — deterministic color complement and scoring utilities.

Callable utility that agents can invoke for color-related styling decisions.
No LLM calls — purely rule-based.
"""

from __future__ import annotations

from backend.schemas.clothing import Color

# ──────────────────────────────────────────────────────────────────────
#  Color complement table
# ──────────────────────────────────────────────────────────────────────

COLOR_COMPLEMENTS: dict[Color, list[Color]] = {
    Color.BLACK: [Color.WHITE, Color.RED, Color.GREY, Color.PINK, Color.BEIGE, Color.CREAM],
    Color.WHITE: [Color.BLACK, Color.NAVY, Color.BLUE, Color.RED, Color.GREY, Color.BEIGE],
    Color.RED: [Color.BLACK, Color.WHITE, Color.NAVY, Color.GREY, Color.CREAM],
    Color.BLUE: [Color.WHITE, Color.BEIGE, Color.GREY, Color.BROWN, Color.CREAM],
    Color.NAVY: [Color.WHITE, Color.BEIGE, Color.CREAM, Color.GREY, Color.BROWN, Color.PINK],
    Color.GREEN: [Color.WHITE, Color.BEIGE, Color.BROWN, Color.CREAM, Color.BLACK],
    Color.YELLOW: [Color.NAVY, Color.GREY, Color.BLACK, Color.WHITE, Color.BLUE],
    Color.ORANGE: [Color.NAVY, Color.WHITE, Color.BLUE, Color.BROWN, Color.CREAM],
    Color.PINK: [Color.NAVY, Color.GREY, Color.WHITE, Color.BLACK, Color.BLUE],
    Color.PURPLE: [Color.WHITE, Color.GREY, Color.BLACK, Color.BEIGE, Color.CREAM],
    Color.BROWN: [Color.WHITE, Color.BEIGE, Color.CREAM, Color.BLUE, Color.GREEN, Color.NAVY],
    Color.GREY: [Color.BLACK, Color.WHITE, Color.NAVY, Color.BLUE, Color.PINK, Color.RED],
    Color.BEIGE: [Color.NAVY, Color.BROWN, Color.WHITE, Color.OLIVE, Color.BLUE, Color.BLACK],
    Color.CREAM: [Color.NAVY, Color.BROWN, Color.BLACK, Color.OLIVE, Color.BLUE],
    Color.MAROON: [Color.WHITE, Color.BEIGE, Color.CREAM, Color.GREY, Color.NAVY],
    Color.OLIVE: [Color.WHITE, Color.BEIGE, Color.CREAM, Color.BROWN, Color.NAVY],
    Color.TEAL: [Color.WHITE, Color.CREAM, Color.BEIGE, Color.GREY, Color.BROWN],
    Color.OTHER: [Color.WHITE, Color.BLACK, Color.GREY],
}

# Neutral colors that pair broadly.
_NEUTRALS = {Color.BLACK, Color.WHITE, Color.GREY, Color.BEIGE, Color.CREAM, Color.NAVY}


class ColorMatcherTool:
    """Rule-based color matching tool.

    Provides methods for color complement look-ups, compatibility checks,
    and color-pair scoring.  Designed to be called by agents.
    """

    def score_pair(self, base_color: Color, candidate_color: Color) -> float:
        """Score 0-1 for how well *candidate_color* pairs with *base_color*.

        Higher score = better match.  Rank position in the complement
        list drives the score, with neutrals receiving a small bonus.
        """
        complements = COLOR_COMPLEMENTS.get(base_color, [])

        if candidate_color == base_color:
            return 0.6  # same-color pairing: decent but not top-tier

        if candidate_color in complements:
            # Earlier in the list → better match
            idx = complements.index(candidate_color)
            position_score = 1.0 - (idx * 0.1)
            return max(round(position_score, 2), 0.5)

        # Neutrals still get a baseline
        if candidate_color in _NEUTRALS:
            return 0.4

        return 0.2  # poor match
