"""Taste from the wear log, by counting. Pure code: no network, no database.

Each event is an outfit the user wore, saved or skipped. Every item in it gets a vote
(+1 worn, +1 saved, −1 skipped), and so does its (colour family, garment type) pair, so
a new black tee inherits what the user thought of their other black tees.

    smoothed score = sum of votes / (number of votes + PRIOR_VOTES)

It stays in (−1, 1), and the prior keeps one stray skip from sinking an item: one skip
gives −0.25, four skips −0.57. An item's preference is the mean of its own score and its
pair's. ``engine.outfits`` weighs that by ``PREFERENCE_WEIGHT`` and subtracts a penalty
for items worn in the last ``RECENT_DAYS`` days.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from backend.engine.outfits import ClosetItem

Action = Literal["worn", "saved", "skipped"]

VOTE: Mapping[Action, float] = {"worn": 1.0, "saved": 1.0, "skipped": -1.0}
"""Hand-set, not fitted: there is no labelled taste data to fit them on."""
PRIOR_VOTES = 3
"""Acts like 3 neutral votes on every item and pair before any real one."""
RECENT_DAYS = 3
"""Worn on any of the last 3 days → the recently-worn penalty, so the top pick rotates."""


@dataclass(frozen=True)
class WearEvent:
    item_ids: tuple[str, ...]
    action: Action
    day: dt.date


@dataclass(frozen=True)
class ItemStats:
    times_worn: int
    last_worn: dt.date | None


def _pair(item: ClosetItem) -> tuple[str, str]:
    return item.color_family, item.garment_type


def _smoothed[K](votes: Mapping[K, list[float]]) -> dict[K, float]:
    return {key: sum(v) / (len(v) + PRIOR_VOTES) for key, v in votes.items()}


def item_preferences(events: Iterable[WearEvent], closet: Iterable[ClosetItem]) -> dict[str, float]:
    """Preference per closet item id in (−1, 1); items whose pair has no votes are left out (neutral)."""
    items = list(closet)
    by_id = {i.id: i for i in items}
    item_votes: dict[str, list[float]] = defaultdict(list)
    pair_votes: dict[tuple[str, str], list[float]] = defaultdict(list)
    for event in events:
        for item_id in event.item_ids:
            if item_id in by_id:  # deleted items keep their events; they no longer vote
                item_votes[item_id].append(VOTE[event.action])
                pair_votes[_pair(by_id[item_id])].append(VOTE[event.action])
    own, pair = _smoothed(item_votes), _smoothed(pair_votes)
    return {i.id: (own.get(i.id, 0.0) + pair[_pair(i)]) / 2 for i in items if _pair(i) in pair}


def recently_worn(events: Iterable[WearEvent], today: dt.date) -> set[str]:
    """Items worn from ``RECENT_DAYS`` days before *today* up to *today*."""
    since = today - dt.timedelta(days=RECENT_DAYS)
    return {i for e in events if e.action == "worn" and since <= e.day <= today for i in e.item_ids}


def wear_stats(events: Iterable[WearEvent], item_ids: Iterable[str]) -> dict[str, ItemStats]:
    """Times worn and last worn day for each of *item_ids* (0 and None when never worn)."""
    days: dict[str, list[dt.date]] = {i: [] for i in item_ids}
    for event in events:
        if event.action == "worn":
            for item_id in event.item_ids:
                if item_id in days:
                    days[item_id].append(event.day)
    return {i: ItemStats(len(d), max(d, default=None)) for i, d in days.items()}
