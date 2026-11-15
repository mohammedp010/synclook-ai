"""Explanations for built outfits: one text-model call words all of them from their evidence.

The model words; it does not choose. A local check rejects any explanation that
names a garment its outfit does not contain. On a failure the call is retried
once; an outfit whose explanation still fails gets a template sentence built from
the same evidence. Each explanation says which way it was written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.engine.outfits import Outfit
from backend.schemas.taxonomy import AccessoryType, GarmentCategory, GarmentType, Occasion
from backend.services.llm import LLMService

logger = get_logger(__name__)

PROMPT_VERSION = "outfits-v1"
_SYSTEM_PROMPT = (
    "You are a stylist. For each numbered outfit, write one or two sentences (under 45 words) on why it "
    "works for the occasion, using ONLY that outfit's facts. Refer to the pieces by the names given. "
    "Never name a garment or accessory that is not in that outfit. No markdown, no numbers or scores. "
    "Return one explanation per outfit, in order."
)

# Words that name a garment but are also ordinary English, so they cannot be checked.
_AMBIGUOUS = frozenset({"suit", "set", "square", "tie", "flat", "ring", "other"})
# Category words: fine when the outfit has something in that category.
_GENERIC = {
    "shoe": GarmentCategory.FOOTWEAR,
    "footwear": GarmentCategory.FOOTWEAR,
    "top": GarmentCategory.TOPWEAR,
    "bottom": GarmentCategory.BOTTOMWEAR,
    "layer": GarmentCategory.OUTERWEAR,
    "outerwear": GarmentCategory.OUTERWEAR,
    "accessory": GarmentCategory.ACCESSORY,
    "accessorie": GarmentCategory.ACCESSORY,
}
_SYNONYMS = {
    "tee": {"t-shirt"},
    "pant": {"trouser", "jean", "chino", "jogger"},
    "trainer": {"sneaker"},
    "jumper": {"sweater", "sweatshirt"},
    "handbag": {"bag", "clutch"},
    "purse": {"bag", "clutch"},
}
_TOKEN = re.compile(r"[a-z]+(?:-[a-z]+)*")
_DRESS_VERB = re.compile(r"\bdress(?:es|ed)? (?:up|down)\b")


def _norm(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _type_words(garment_type: str) -> set[str]:
    """``t_shirt`` → {"t-shirt"}; ``formal_shoes`` → {"formal-shoe", "shoe"}."""
    parts = garment_type.split("_")
    words = {_norm("-".join(parts))}
    if len(parts) > 1:
        words.add(_norm(parts[-1]))
    return words - _AMBIGUOUS


_VOCAB = frozenset().union(*(_type_words(t.value) for t in (*GarmentType, *AccessoryType))) | set(_SYNONYMS)


def unowned_garments(text: str, outfit: Outfit) -> list[str]:
    """Garment words in *text* that name nothing in *outfit*."""
    have: set[str] = set()
    for item in outfit.items:
        have |= _type_words(item.garment_type)
        have |= {_norm(w) for w in _TOKEN.findall(item.short_label.lower())}
    categories = {item.category for item in outfit.items}
    bad = []
    for raw in _TOKEN.findall(_DRESS_VERB.sub(" ", text.lower())):
        word = _norm(raw)
        if word in have:
            continue
        if word in _GENERIC:
            ok = _GENERIC[word] in categories
        elif word in _SYNONYMS:
            ok = bool(_SYNONYMS[word] & have)
        else:
            ok = word not in _VOCAB
        if not ok:
            bad.append(raw)
    return bad


def template(outfit: Outfit, occasion: Occasion) -> str:
    names = [i.short_label for i in outfit.items]
    pieces = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
    colour = next((f for f in outfit.evidence if "pairs well" in f), None)
    tail = f" The {colour.split(':')[0]} pair well." if colour else ""
    return f"{pieces[0].upper()}{pieces[1:]}: all suit {occasion.value.replace('_', ' ')}.{tail}"


class _Explanations(BaseModel):
    explanations: list[str]


@dataclass(frozen=True)
class Explanation:
    text: str
    source: Literal["model", "template"]


def _prompt(outfits: list[Outfit], occasion: Occasion, weather_line: str | None) -> str:
    lines = [f"Occasion: {occasion.value.replace('_', ' ')}"]
    if weather_line:
        lines.append(f"Weather: {weather_line}")
    for n, outfit in enumerate(outfits, start=1):
        lines.append(f"\nOutfit {n} pieces: " + "; ".join(i.short_label for i in outfit.items))
        lines += [f"- {fact}" for fact in outfit.evidence]
    return "\n".join(lines)


async def explain(
    llm: LLMService, outfits: list[Outfit], occasion: Occasion, weather_line: str | None = None
) -> list[Explanation]:
    """One explanation per outfit, in order. Never raises for a model failure."""
    if not outfits:
        return []
    final: list[Explanation | None] = [None] * len(outfits)
    for attempt in (1, 2):
        try:
            reply = await llm.structured(
                _Explanations, system_prompt=_SYSTEM_PROMPT, user_prompt=_prompt(outfits, occasion, weather_line)
            )
        except LLMError as exc:
            logger.warning("explanation_call_failed", attempt=attempt, error=exc.message)
            continue
        texts = reply.explanations
        if len(texts) != len(outfits):
            logger.warning("explanation_count_mismatch", attempt=attempt, got=len(texts), want=len(outfits))
            continue
        for n, (text, outfit) in enumerate(zip(texts, outfits, strict=True)):
            bad = unowned_garments(text, outfit)
            if final[n] is None and text.strip() and not bad:
                final[n] = Explanation(text.strip(), "model")
            elif bad:
                logger.warning("explanation_names_unowned", attempt=attempt, outfit=n, words=bad)
        if all(final):
            break
    return [e or Explanation(template(o, occasion), "template") for e, o in zip(final, outfits, strict=True)]
