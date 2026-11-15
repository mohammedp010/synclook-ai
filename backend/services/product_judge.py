"""Product relevance from Jev — is this listing the item the shopper asked for?

The live shopping path gets product *titles* back from the provider and has to
decide which ones are the slot it searched for. The CLIP matcher answers that
with a type/colour/gender softmax over the title plus a cosine threshold: a
scale it shares with nothing, and a vocabulary that has no "belt" or "silver"
(accessories are gated at category level, so a belt bag passes as a belt).

Jev reads the title as words. Three **atomic** nouls per product (reference
§7.1 — one condition per noul, combined in code):

- ``item`` — is the listing the item itself, not a part, a holder, or a
  different item that shares its name (belt bag, watch strap, tie clip);
- ``colour`` — does it name the wanted colour or a shade of it, rather than a
  neighbouring named colour (ivory for white, olive for green);
- ``buyer`` — is it sold for the wanted buyer (not the other gender, not kids).

Two ways to ask, both measured by ``evaluation/product_relevance.py``:
``batched`` puts the slot's titles in one state and asks 3·N questions in one
call (speculative fan-out, §7.2); ``isolated`` makes one call per product so no
title is a distractor for another (§8.5). ``ProductJudge.batched`` picks.

Questions only; the bar is ``core.product_policy``. ``gate`` is the whole product
gate (buyer policy in code, then Jev). Jev failures propagate — ``POST /shop/search``
then shows no products and says so.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.core.logging import get_logger
from backend.core.product_policy import CALIBRATED_FOR, PRODUCT_THRESHOLD
from backend.schemas.api import ProductLink
from backend.services.jev import JevClient, Noul, Question
from backend.tools.style_rules import INVALID_ITEMS_BY_SHOPPING_INTENT, normalize_shopping_intent

logger = get_logger(__name__)

_BUYER = {
    "menswear": ("adult men", "Men's or unisex, or no audience is named"),
    "womenswear": ("adult women", "Women's or unisex, or no audience is named"),
}
_ANY_ADULT = ("adults", "Men's, women's or unisex, or no audience is named")
_NO_COLOUR = frozenset({"", "other", "neutral", "multicolor"})


@dataclass(frozen=True)
class Wanted:
    """The outfit slot, in words."""

    item: str
    """``"belt"``, ``"t-shirt"``, ``"pocket square"`` — a taxonomy value with spaces."""
    colour: str | None
    shopping_intent: str
    """``menswear`` | ``womenswear`` | anything else (treated as any adult)."""

    @property
    def has_colour(self) -> bool:
        return (self.colour or "").strip().lower() not in _NO_COLOUR


@dataclass(frozen=True)
class ProductVerdict:
    p_item: float
    p_colour: float
    """1.0 when the slot names no colour to check."""
    p_buyer: float

    @property
    def relevance(self) -> float:
        return self.p_item * self.p_colour * self.p_buyer

    @property
    def keep(self) -> bool:
        return min(self.p_item, self.p_colour, self.p_buyer) >= PRODUCT_THRESHOLD

    def facts(self) -> list[str]:
        return [f"jev: item {self.p_item:.2f}, colour {self.p_colour:.2f}, buyer {self.p_buyer:.2f}"]


def _article(word: str) -> str:
    if word.endswith("s") and word not in {"dress"}:
        return "a pair of " if word in {"shoes", "sunglasses", "earrings", "jeans", "trousers", "shorts"} else ""
    return "an " if word[0] in "aeiou" else "a "


def build_questions(wanted: Wanted, ref: str) -> dict[str, Question]:
    """The three nouls about the listing at state path ``ref`` (e.g. ``products[3]``)."""
    item = wanted.item
    audience, audience_true = _BUYER.get(wanted.shopping_intent, _ANY_ADULT)
    questions: dict[str, Question] = {
        "item": Noul(
            f"Is the product listed in `{ref}` {_article(item)}{item} itself?",
            true=f"The listing is for {_article(item)}{item}, the thing a shopper searching for one wants",
            false=(
                "It is a different item, even one with a similar name, or a part, refill, holder, case, "
                f"organiser or care product for {_article(item)}{item}, or an outfit or fabric set built "
                "around another garment"
            ),
        ),
        "buyer": Noul(
            f"Is the product listed in `{ref}` sold for {audience}?",
            true=audience_true,
            false="It is named as being for another gender, or for kids, boys, girls or babies",
        ),
    }
    if wanted.has_colour:
        colour = (wanted.colour or "").replace("_", " ")
        questions["colour"] = Noul(
            f"Is the product listed in `{ref}` {colour}?",
            true=f"Its listing names {colour}, or a lighter or darker shade sold as {colour}",
            false=(
                "It names a different colour, including a neighbouring colour with its own name "
                "(ivory or off-white instead of white, olive instead of green, burgundy instead of red), "
                "or names no colour at all"
            ),
        )
    return questions


def _verdict(answers: dict[str, float], wanted: Wanted) -> ProductVerdict:
    return ProductVerdict(
        p_item=answers["item"],
        p_colour=answers["colour"] if wanted.has_colour else 1.0,
        p_buyer=answers["buyer"],
    )


class ProductJudge:
    def __init__(self, client: JevClient | None = None, *, batched: bool = True) -> None:
        self._client = client or JevClient()
        self.batched = batched

    @property
    def enabled(self) -> bool:
        return self._client.enabled

    async def aclose(self) -> None:
        await self._client.aclose()

    async def judge(self, wanted: Wanted, titles: list[str]) -> list[ProductVerdict]:
        if not titles:
            return []
        if self.batched:
            return await self._judge_batched(wanted, titles)
        return list(await asyncio.gather(*(self._judge_one(wanted, t) for t in titles)))

    async def _judge_batched(self, wanted: Wanted, titles: list[str]) -> list[ProductVerdict]:
        questions: dict[str, Question] = {}
        for i in range(len(titles)):
            for name, q in build_questions(wanted, f"products[{i}]").items():
                questions[f"p{i}_{name}"] = q
        resp = await self._client.judge({"products": titles}, questions)
        self._check_model(resp.model)
        return [
            _verdict(
                {
                    name: resp.noul(f"p{i}_{name}").p
                    for name in ("item", "colour", "buyer")
                    if f"p{i}_{name}" in questions
                },
                wanted,
            )
            for i in range(len(titles))
        ]

    async def _judge_one(self, wanted: Wanted, title: str) -> ProductVerdict:
        questions = build_questions(wanted, "product")
        resp = await self._client.judge({"product": title}, questions)
        self._check_model(resp.model)
        return _verdict({name: resp.noul(name).p for name in questions}, wanted)

    @staticmethod
    def _check_model(model: str) -> None:
        if model != CALIBRATED_FOR:
            logger.warning("product_policy_uncalibrated", calibrated_for=CALIBRATED_FOR, answered=model)


def loggable(verdicts: list[ProductVerdict]) -> list[dict[str, Any]]:
    return [
        {"item": round(v.p_item, 3), "colour": round(v.p_colour, 3), "buyer": round(v.p_buyer, 3)} for v in verdicts
    ]


async def gate(judge: ProductJudge, products: list[ProductLink], wanted: Wanted) -> list[ProductLink]:
    """The product gate: kept products, best first. Raises ``JevError``.

    Code runs first (a men's search drops titles naming a dress, skirt or blouse), then
    Jev's three nouls; a product is kept when all three clear ``PRODUCT_THRESHOLD`` and is
    ranked by their product. Measured: held-out F1 0.946 (``evaluation/product_relevance.py``).
    """
    invalid = {
        t.value for t in INVALID_ITEMS_BY_SHOPPING_INTENT.get(normalize_shopping_intent(wanted.shopping_intent), set())
    }
    pool = [p for p in products if not any(term in p.title.lower() for term in invalid)]
    if not pool:
        return []
    verdicts = await judge.judge(wanted, [p.title for p in pool])
    logger.info("product_judged", item=wanted.item, colour=wanted.colour, verdicts=loggable(verdicts))
    kept = [
        p.model_copy(
            update={
                "match_score": round(v.relevance, 2),
                "match_evidence": v.facts(),
                "match_reason": "; ".join(v.facts()),
            }
        )
        for p, v in zip(pool, verdicts, strict=True)
        if v.keep
    ]
    return sorted(kept, key=lambda p: p.match_score, reverse=True)
