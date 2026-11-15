"""Live smoke test against the real Jev API — skipped unless ``JEV_API_KEY`` is set.

One request, three questions, a fraction of a cent. It checks the things the
mocked tests cannot: that the documented wire format is the real one, that the
pinned model id is accepted, and that the response's ``model`` is the pinned id
rather than wherever an alias has moved to.

    JEV_API_KEY=... poetry run pytest tests/integration/test_jev_live.py -v -s
"""

from __future__ import annotations

import pytest

from backend.core.config import get_settings
from backend.services.jev import Choice, JevClient, Noul, Score

pytestmark = pytest.mark.skipif(not get_settings().jev_api_key, reason="JEV_API_KEY not set")


async def test_live_round_trip_returns_typed_answers_from_the_pinned_model() -> None:
    client = JevClient()
    try:
        resp = await client.judge(
            {"garment": "A navy single-breasted wool blazer with notch lapels and two buttons."},
            {
                "client_meeting": Noul(
                    "Would a well-dressed person wear this garment to a client meeting?",
                    true="Appropriate for a client meeting",
                    false="Out of place at a client meeting",
                ),
                "beach_day": Noul(
                    "Would a well-dressed person wear this garment to a beach day?",
                    true="Appropriate for a beach day",
                    false="Out of place at a beach day",
                ),
                "category": Choice(
                    "What kind of garment is `garment`?",
                    {
                        "topwear": "Shirts, t-shirts, sweaters, blouses",
                        "outerwear": "Jackets, blazers, coats worn over other layers",
                        "bottomwear": "Trousers, jeans, skirts, shorts",
                        "other": None,
                    },
                ),
                "formality": Score(
                    "How formal is `garment`?",
                    (
                        "Loungewear or gym clothes",
                        "Everyday casual: tees, hoodies, jeans",
                        "Smart casual: chinos, polos, unstructured jackets",
                        "Business: suits, blazers, dress shirts",
                        "Black tie: tuxedos, evening gowns",
                    ),
                ),
            },
        )
    finally:
        await client.aclose()

    print(f"\nmodel={resp.model} tokens={resp.input_tokens} latency={resp.latency_ms}ms")
    for key, answer in resp.answers.items():
        print(f"  {key}: {answer}")

    assert resp.model == get_settings().jev_model
    # Sanity, not calibration: a navy blazer is meeting-wear, not beachwear.
    assert resp.noul("client_meeting").p > resp.noul("beach_day").p
    assert resp.choice("category").choice in {"outerwear", "topwear"}
    assert 0.0 <= resp.score("formality").score <= 4.0
