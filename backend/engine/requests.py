"""What the user asked to wear that the closet does not have (pure code, no model).

"Swimwear for a pool party" with no swimwear must be answered "you have none" first, not with a
t-shirt and shorts called swimwear (the Phase 8 head-to-head: Synclook said so on 1 of 4 such
requests, a plain chatbot on 4 of 4). The words come from the taxonomy, plus a few things no closet
here can hold because perception has no tag for them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from backend.schemas.taxonomy import AccessoryType, GarmentType

# Never tagged by perception, so always missing when asked for.
_OUTSIDE = {
    "swimwear": r"swim\w*|bikinis?|board ?shorts",
    "tuxedo": r"tux(?:edo)?(?:e?s)?|dinner jackets?",
    "ski gear": r"ski(?:s|ing)?",
}
# Also everyday words ("suit the weather", "black tie", "dress up", "a short walk", "watch a film"): not checked.
# shortcut: skipping them misses "my suit" or "a tie"; upgrade to a parser if users ask for those often.
_AMBIGUOUS = {"suit", "tie", "dress", "shorts", "flats", "watch", "stole", "rings", "other", "cap"}


def _pattern(phrase: str) -> str:
    base = phrase[:-1] if phrase.endswith("s") and not phrase.endswith("ss") else phrase
    return base.replace(" ", r"[ -]?") + r"(?:e?s)?"


_TYPES = {
    t.value: _pattern(t.value.replace("_", " ")) for t in (*GarmentType, *AccessoryType) if t.value not in _AMBIGUOUS
}
PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"\b(?:{p})\b", re.I)
    for name, p in ({k.replace("_", " "): v for k, v in _TYPES.items()} | _OUTSIDE).items()
}


def _owned(name: str, garment_types: set[str]) -> bool:
    key = name.replace(" ", "_")
    # A request for a "jacket" is met by a denim jacket, a "coat" by a trench coat.
    return any(g == key or g.endswith(f"_{key}") for g in garment_types)


def missing_requested(texts: Iterable[str], garment_types: Iterable[str]) -> list[str]:
    """Items named in *texts* (the user's words, the model's ``requested`` list) that no closet item is."""
    owned = set(garment_types)
    text = " ".join(texts)
    return [name for name, rx in PATTERNS.items() if rx.search(text) and not _owned(name, owned)]


_NEGATION = re.compile(r"\b(?:no|not|none|without|lack\w*|missing|cannot)\b|n['’]t\b", re.I)


def says_missing(name: str, text: str) -> bool:
    """Does *text* tell the user *name* is not there: the item and a negation in one sentence?
    ("Here are some swimwear outfits" names it and is exactly the answer this exists to stop.)"""
    return any(PATTERNS[name].search(s) and _NEGATION.search(s) for s in re.split(r"[.!?\n]+", text))
