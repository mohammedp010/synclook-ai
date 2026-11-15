"""Wear-log learning: the counting rules, then the proof that a hidden taste moves the ranking."""

from __future__ import annotations

import datetime as dt

import pytest

from backend.engine.outfits import ClosetItem, Outfit, build_outfits
from backend.engine.preferences import (
    WearEvent,
    item_preferences,
    recently_worn,
    wear_stats,
)
from backend.schemas.taxonomy import ColorName, GarmentCategory, Occasion
from evaluation.outfit_engine import demo_closet
from tests.unit.engine.test_outfits import item

DAY = dt.date(2026, 11, 1)
TEE = item("tee", "t_shirt", GarmentCategory.TOPWEAR)
TEE2 = item("tee2", "t_shirt", GarmentCategory.TOPWEAR)
JEANS = item("jeans", "jeans", GarmentCategory.BOTTOMWEAR, ColorName.BLUE, "blue")


def _event(action: str, *ids: str, day: dt.date = DAY) -> WearEvent:
    return WearEvent(tuple(ids), action, day)  # type: ignore[arg-type]


def test_votes_are_smoothed_and_shared_with_the_colour_type_pair() -> None:
    prefs = item_preferences([_event("skipped", "tee")], [TEE, TEE2, JEANS])
    assert prefs["tee"] == pytest.approx(-0.25)  # own −1/4, pair −1/4
    assert prefs["tee2"] == pytest.approx(-0.125)  # no own votes, inherits the navy-tee pair
    assert "jeans" not in prefs  # nothing known → neutral
    many = item_preferences([_event("worn", "tee")] * 20, [TEE])
    assert 0.8 < many["tee"] < 1.0


def test_worn_and_saved_raise_skipped_lowers_and_unknown_ids_are_ignored() -> None:
    events = [_event("worn", "tee", "gone"), _event("saved", "jeans"), _event("skipped", "jeans")]
    prefs = item_preferences(events, [TEE, JEANS])
    assert prefs["tee"] > 0 and prefs["jeans"] == 0
    assert set(prefs) == {"tee", "jeans"}


def test_recently_worn_covers_the_last_three_days_and_only_wearing() -> None:
    events = [
        _event("worn", "a", day=DAY - dt.timedelta(days=3)),
        _event("worn", "old", day=DAY - dt.timedelta(days=4)),
        _event("saved", "s", day=DAY),
        _event("worn", "future", day=DAY + dt.timedelta(days=1)),
    ]
    assert recently_worn(events, DAY) == {"a"}


def test_stats_count_wears_and_find_the_last_day() -> None:
    events = [_event("worn", "tee", "jeans"), _event("worn", "tee", day=DAY + dt.timedelta(days=2))]
    stats = wear_stats([*events, _event("skipped", "tee")], ["tee", "jeans", "never"])
    assert (stats["tee"].times_worn, stats["tee"].last_worn) == (2, DAY + dt.timedelta(days=2))
    assert (stats["jeans"].times_worn, stats["never"].times_worn, stats["never"].last_worn) == (1, 0, None)


# ── The proof: a simulated user with a hidden taste ──────────────────

DARK = frozenset({"black", "navy", "grey"})
OCCASIONS = list(Occasion)


def _dark_share(outfit: Outfit) -> float:
    garments = [i for i in outfit.items if i.category != GarmentCategory.ACCESSORY]
    return sum(i.color_family in DARK for i in garments) / len(garments)


def _ranking(closet: list[ClosetItem], events: list[WearEvent]) -> tuple[float, float]:
    """Over all occasions: mean dark share of the #1 outfit, and how often #1 is one the user likes."""
    prefs = item_preferences(events, closet)
    tops = [r.outfits[0] for o in OCCASIONS if (r := build_outfits(closet, o, preferences=prefs)).outfits]
    return sum(map(_dark_share, tops)) / len(tops), sum(_dark_share(t) >= 0.5 for t in tops) / len(tops)


def simulate(days: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """One occasion a day. The user wears the first suggestion that is mostly dark and skips the rest that are not."""
    closet = demo_closet()
    events: list[WearEvent] = []
    before = _ranking(closet, events)
    for n in range(days):
        today = DAY + dt.timedelta(days=n)
        suggested = build_outfits(
            closet,
            OCCASIONS[n % len(OCCASIONS)],
            preferences=item_preferences(events, closet),
            recently_worn=recently_worn(events, today),
        ).outfits
        liked = [o for o in suggested if _dark_share(o) >= 0.5]
        if liked:
            events.append(WearEvent(liked[0].item_ids, "worn", today))
        events += [WearEvent(o.item_ids, "skipped", today) for o in suggested if _dark_share(o) < 0.5]
    return before, _ranking(closet, events)


def test_a_hidden_taste_for_dark_colours_moves_the_ranking_toward_it() -> None:
    (share0, hit0), (share1, hit1) = simulate(days=28)
    assert share1 > share0 + 0.1
    assert hit1 > hit0
