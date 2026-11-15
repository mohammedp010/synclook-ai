"""The explainer: one call for all outfits, a local garment check, one retry, then a template."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.exceptions import LLMError
from backend.engine.outfits import Outfit, build_outfits
from backend.schemas.taxonomy import Occasion
from backend.services.outfit_explainer import _Explanations, explain, template, unowned_garments
from evaluation.outfit_engine import demo_closet

OUTFITS = build_outfits(demo_closet(), Occasion.BUSINESS_FORMAL).outfits
TWO_PIECE = next(o for o in OUTFITS if any(i.garment_type == "trousers" for i in o.items))


def _llm(*replies: list[str] | Exception) -> AsyncMock:
    llm = AsyncMock()
    llm.structured = AsyncMock(
        side_effect=[r if isinstance(r, Exception) else _Explanations(explanations=r) for r in replies]
    )
    return llm


def _labels(outfit: Outfit) -> str:
    return " and ".join(i.short_label for i in outfit.items)


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("The cream blouse and beige trousers look sharp.", []),
        ("Add your black blazer and polished loafers.", []),
        ("Your shoes and top work together.", []),  # category words, and the outfit has both
        ("Swap in a pair of jeans for the weekend.", ["jeans"]),
        ("A silk tie finishes it.", []),  # 'tie' is also a verb: not checkable
        ("A red scarf and sneakers would also work.", ["scarf", "sneakers"]),
        ("These pants are tailored.", []),  # synonym of the trousers in the outfit
        ("Dress up the look with a tee.", ["tee"]),  # 'dress up' is a verb; 'tee' is not here
        ("Wear the jeans.", ["jeans"]),
    ],
)
def test_unowned_garments(text: str, bad: list[str]) -> None:
    assert unowned_garments(text, TWO_PIECE) == bad


async def test_one_call_words_every_outfit() -> None:
    llm = _llm([f"{_labels(o)} suit the office." for o in OUTFITS])
    result = await explain(llm, OUTFITS, Occasion.BUSINESS_FORMAL)
    assert [e.source for e in result] == ["model"] * len(OUTFITS)
    assert llm.structured.await_count == 1
    prompt = llm.structured.await_args.kwargs["user_prompt"]
    assert all(fact in prompt for fact in OUTFITS[0].evidence)


async def test_an_invented_garment_is_retried_once_then_kept_when_fixed() -> None:
    good = [f"{_labels(o)} suit the office." for o in OUTFITS]
    bad = ["Wear it with sneakers.", *good[1:]]
    result = await explain(_llm(bad, good), OUTFITS, Occasion.BUSINESS_FORMAL)
    assert [e.source for e in result] == ["model"] * len(OUTFITS)
    assert result[0].text == good[0]


async def test_still_wrong_after_the_retry_becomes_a_template() -> None:
    good = [f"{_labels(o)} suit the office." for o in OUTFITS]
    bad = ["Wear it with sneakers.", *good[1:]]
    llm = _llm(bad, bad)
    result = await explain(llm, OUTFITS, Occasion.BUSINESS_FORMAL)
    assert llm.structured.await_count == 2
    assert result[0].source == "template" and result[0].text == template(OUTFITS[0], Occasion.BUSINESS_FORMAL)
    assert [e.source for e in result[1:]] == ["model"] * (len(OUTFITS) - 1)
    assert unowned_garments(result[0].text, OUTFITS[0]) == []


@pytest.mark.parametrize("failure", [LLMError("down"), ["only one"]])
async def test_model_failure_or_wrong_count_falls_back_to_templates(failure: list[str] | Exception) -> None:
    result = await explain(_llm(failure, failure), OUTFITS, Occasion.BUSINESS_FORMAL)
    assert [e.source for e in result] == ["template"] * len(OUTFITS)


async def test_no_outfits_no_call() -> None:
    llm = _llm()
    assert await explain(llm, [], Occasion.INTERVIEW) == []
    llm.structured.assert_not_awaited()


def test_the_outfits_own_words_always_pass() -> None:
    renamed = TWO_PIECE.items[0].model_copy(update={"short_label": "white tee"})
    outfit = Outfit((renamed, *TWO_PIECE.items[1:]), TWO_PIECE.score, TWO_PIECE.score_parts, TWO_PIECE.evidence)
    assert unowned_garments("The white tee and beige trousers work.", outfit) == []
