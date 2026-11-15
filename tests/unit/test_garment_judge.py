"""Tests for the Jev garment judge and the occasion policy.

Mocked Jev throughout. What is pinned here is the *shape* of the decision —
occasion as N independent nouls, thresholds owned by code — not whether Jev's
judgments are good; that is the perception eval's job.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.core import occasion_policy
from backend.core.config import Settings
from backend.schemas.taxonomy import AccessoryType, Aesthetic, Formality, Occasion
from backend.services.garment_judge import (
    GarmentDescription,
    GarmentJudge,
    build_questions,
)
from backend.services.jev import Choice, JevClient, Noul, Score

PINNED = "jev-1.13.0"


def _answers(occasion_p: dict[Occasion, float], formality: float = 2.0, aesthetic: str = "classic") -> dict[str, Any]:
    answers: dict[str, Any] = {
        f"occ_{occ.value}": {"type": "noul", "noul": occasion_p.get(occ, 0.1)} for occ in Occasion
    }
    answers["formality"] = {
        "type": "score",
        "score": formality,
        "probabilities": {str(i): (1.0 if i == round(formality) else 0.0) for i in range(5)},
        "confidence": 0.9,
    }
    answers["garment_type"] = {
        "type": "choice",
        "choice": "blazer",
        "probabilities": {"blazer": 0.9, "jacket": 0.1},
        "confidence": 0.85,
    }
    answers["garment_photo"] = {"type": "noul", "noul": 0.95}
    answers["warmth"] = {"type": "choice", "choice": "medium", "probabilities": {"medium": 0.8}, "confidence": 0.8}
    answers["aesthetic"] = {
        "type": "choice",
        "choice": aesthetic,
        "probabilities": {a.value: (1.0 if a.value == aesthetic else 0.0) for a in Aesthetic},
        "confidence": 0.8,
    }
    return answers


def _judge(answers: dict[str, Any], seen: dict[str, Any] | None = None) -> GarmentJudge:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            import json

            seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": PINNED, "answers": answers, "usage": {"input_tokens": 900}})

    settings = Settings(jev_api_key="k", jev_base_url="https://api.typesafe.ai", jev_model=PINNED)
    return GarmentJudge(JevClient(settings=settings, transport=httpx.MockTransport(handler)))


# ── Questions ────────────────────────────────────────────────────────


def test_every_occasion_is_its_own_noul() -> None:
    # Occasion fit is not mutually exclusive, so it must never be a Choice:
    # a choice's probabilities sum to 1 and would force occasions to compete.
    questions = build_questions()
    for occ in Occasion:
        assert isinstance(questions[f"occ_{occ.value}"], Noul)
    assert isinstance(questions["formality"], Score)
    assert isinstance(questions["aesthetic"], Choice)
    assert isinstance(questions["garment_type"], Choice)
    assert isinstance(questions["garment_photo"], Noul)
    assert len(questions) == len(Occasion) + 5


def test_aesthetic_choice_has_an_escape_and_formality_follows_the_ladder() -> None:
    questions = build_questions()
    aesthetic = questions["aesthetic"]
    formality = questions["formality"]
    assert isinstance(aesthetic, Choice) and isinstance(formality, Score)
    assert "other" in aesthetic.options
    assert len(formality.levels) == len(Formality)


def test_state_carries_words_not_codes() -> None:
    state = GarmentDescription("blazer", colour="light_grey", pattern="solid").to_state()
    assert state == {"garment": "blazer", "colour": "light grey"}  # solid adds nothing


# ── Judging ──────────────────────────────────────────────────────────


async def test_judgment_parses_and_applies_the_policy() -> None:
    probs = {Occasion.INTERVIEW: 0.96, Occasion.BUSINESS_FORMAL: 0.9, Occasion.WEDDING_GUEST: 0.55}
    seen: dict[str, Any] = {}
    judge = _judge(_answers(probs, formality=3.2, aesthetic="classic"), seen)
    result = await judge.judge(GarmentDescription("blazer", colour="navy"))
    await judge.aclose()

    assert result.occasions == [Occasion.INTERVIEW, Occasion.BUSINESS_FORMAL, Occasion.WEDDING_GUEST]
    assert result.occasion_p[Occasion.GYM_ATHLEISURE] == pytest.approx(0.1)
    assert result.formality == Formality.BUSINESS_FORMAL
    assert result.aesthetic == Aesthetic.CLASSIC
    assert seen["body"]["state"] == {"garment": "blazer", "colour": "navy"}
    assert result.garment_type == "blazer"
    # One call, fan-out: occasions and the five single questions.
    assert len(seen["body"]["questions"]) == len(Occasion) + 5


def test_policy_threshold_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    probs = {Occasion.BEACH_RESORT: 0.55, Occasion.LOUNGEWEAR: 0.45}
    assert occasion_policy.occasions_from(probs) == [Occasion.BEACH_RESORT]
    monkeypatch.setitem(occasion_policy.OCCASION_THRESHOLD_OVERRIDES, Occasion.BEACH_RESORT, 0.6)
    monkeypatch.setitem(occasion_policy.OCCASION_THRESHOLD_OVERRIDES, Occasion.LOUNGEWEAR, 0.4)
    assert occasion_policy.occasions_from(probs) == [Occasion.LOUNGEWEAR]


def test_garment_type_options_cover_the_taxonomy_with_an_escape() -> None:
    from backend.schemas.taxonomy import GarmentType
    from backend.services.garment_judge import GARMENT_TYPE_OPTIONS

    assert "other" in GARMENT_TYPE_OPTIONS
    assert {"loafers", "belt", "lehenga"} <= set(GARMENT_TYPE_OPTIONS)
    assert len(GARMENT_TYPE_OPTIONS) == len(GarmentType) + len(AccessoryType) - 1  # both OTHERs → one


def test_vlm_fields_reach_the_state() -> None:
    state = GarmentDescription(
        "denim jacket",
        colour="denim_blue",
        fabric="denim",
        fit="relaxed",
        detail="metal buttons",
        other_garments=("black jeans",),
    ).to_state()
    assert state == {
        "garment": "denim jacket",
        "colour": "denim blue",
        "fabric": "denim",
        "fit": "relaxed",
        "detail": "metal buttons",
        "also_visible": ["black jeans"],
    }
