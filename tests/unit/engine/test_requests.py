"""Requested items the closet lacks: the four Phase 8 requests, and no false alarms on ordinary words."""

from __future__ import annotations

from backend.engine.requests import missing_requested, says_missing

DEMO = {"t_shirt", "polo", "hoodie", "shirt", "jeans", "shorts", "dress", "blazer", "denim_jacket", "trench_coat",
        "sneakers", "loafers", "boots", "watch", "belt"}  # fmt: skip


def test_the_four_requests_the_closet_cannot_serve() -> None:
    assert missing_requested(["Pool party, I'm going to swim. What swimwear outfit?"], DEMO) == ["swimwear"]
    assert missing_requested(["Black-tie gala: a tuxedo look with a bow tie"], DEMO) == ["bow tie", "tuxedo"]
    assert missing_requested(["Skiing trip in the snow. What ski outfit?"], DEMO) == ["ski gear"]
    assert missing_requested(["I want to wear heels with my dress"], DEMO) == ["heels"]


def test_owned_items_and_everyday_words_are_not_missing() -> None:
    for text in [
        "Office outfit, but not the black loafers", "My white sneakers are in the wash",
        "How should I dress for a short walk? Something to suit the weather, black tie optional",
        "A jacket and a coat for the rain",  # met by the denim jacket and the trench coat
        "Board meeting with clients", "I'll watch a film after",
    ]:  # fmt: skip
        assert missing_requested([text], DEMO) == [], text


def test_the_models_requested_list_counts_and_forms_are_matched() -> None:
    assert missing_requested(["", "Heel"], DEMO) == ["heels"]
    assert says_missing("swimwear", "You don’t have a swimsuit.") and says_missing("heels", "No heels yet")
    assert not says_missing("swimwear", "Here are some swimwear outfits. Not bad!")  # named, not denied
    assert not says_missing("tuxedo", "Here is a sharp blazer look")
