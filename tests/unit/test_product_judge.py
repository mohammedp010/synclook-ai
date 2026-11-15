"""Tests for the Jev product judge (Phase 6).

Mocked Jev throughout. Pinned here: three atomic nouls per product, the colour
noul skipped when the slot names no colour, one call per slot when batched, and
the keep/rank rule owned by ``product_policy``. Whether Jev reads titles well
is ``evaluation/product_relevance.py``'s job.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.core.config import Settings
from backend.core.product_policy import PRODUCT_THRESHOLD
from backend.services.jev import JevClient
from backend.services.product_judge import ProductJudge, ProductVerdict, Wanted, build_questions


def _judge(p: dict[str, float], *, batched: bool = True) -> tuple[ProductJudge, list[Any]]:
    """Every noul whose key ends in a name in ``p`` answers that probability."""
    sent: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        answers = {key: {"type": "noul", "noul": p[key.rsplit("_", 1)[-1]]} for key in body["questions"]}
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": answers})

    client = JevClient(settings=Settings(jev_api_key="k"), transport=httpx.MockTransport(handler))
    return ProductJudge(client, batched=batched), sent


def test_three_atomic_questions_with_the_item_and_colour_in_words() -> None:
    questions = build_questions(Wanted("pocket square", "white", "menswear"), "products[0]")
    assert set(questions) == {"item", "colour", "buyer"}
    assert "pocket square" in str(questions["item"].to_json())
    assert "`products[0]`" in str(questions["colour"].to_json())


def test_no_colour_question_when_the_slot_names_none() -> None:
    assert "colour" not in build_questions(Wanted("belt", "other", "unisex"), "product")


async def test_batched_is_one_call_per_slot() -> None:
    judge, sent = _judge({"item": 0.9, "colour": 0.8, "buyer": 0.95})
    verdicts = await judge.judge(Wanted("belt", "black", "menswear"), ["Black belt", "Black belt bag", "Brown belt"])
    assert len(sent) == 1
    assert sent[0]["state"] == {"products": ["Black belt", "Black belt bag", "Brown belt"]}
    assert len(sent[0]["questions"]) == 9
    assert len(verdicts) == 3


async def test_isolated_is_one_call_per_product() -> None:
    judge, sent = _judge({"item": 0.9, "colour": 0.8, "buyer": 0.95}, batched=False)
    await judge.judge(Wanted("belt", "black", "menswear"), ["Black belt", "Brown belt"])
    assert [body["state"] for body in sent] == [{"product": "Black belt"}, {"product": "Brown belt"}]


async def test_missing_colour_counts_as_certain() -> None:
    judge, _ = _judge({"item": 0.9, "buyer": 0.9})
    [verdict] = await judge.judge(Wanted("belt", None, "unisex"), ["Leather belt"])
    assert verdict.p_colour == 1.0


def test_keep_needs_every_noul_over_the_bar() -> None:
    assert ProductVerdict(0.9, 0.9, 0.9).keep
    assert not ProductVerdict(0.99, PRODUCT_THRESHOLD - 0.01, 0.99).keep
    assert ProductVerdict(0.9, 0.8, 1.0).relevance == 0.9 * 0.8
