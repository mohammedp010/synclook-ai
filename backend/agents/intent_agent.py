"""Intent Agent — turns the user's free-text request into structured constraints.

LLM proposes, rules validate: extraction runs through DeepSeek structured
output when available, then ``StyleIntent.normalized()`` applies deterministic
clamping. Without an API key (or on LLM failure) a keyword/regex heuristic
provides a conservative fallback, so the pipeline's behavior degrades
gracefully instead of losing the feature entirely.
"""

from __future__ import annotations

import re

from backend.agents.base import AgentContext, BaseAgent
from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.schemas.clothing import Style
from backend.schemas.intent import StyleIntent
from backend.services.llm import LLMService

logger = get_logger(__name__)

# "under ₹5000", "below 3,000 rupees", "less than 2000"
_BUDGET_RE = re.compile(r"(?:under|below|less than|within|max|budget of)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", re.IGNORECASE)

_CLIMATE_KEYWORDS = {
    "rainy": ["rain", "rainy", "monsoon", "drizzle"],
    "cold": ["cold", "winter", "chilly", "snow"],
    "hot": ["hot", "summer", "humid", "heat"],
}

# Occasion keywords → (occasion label, style leaning in catalog taxonomy)
_OCCASION_KEYWORDS: list[tuple[str, str, Style]] = [
    ("office", "office", Style.SMART_CASUAL),
    ("work", "work", Style.SMART_CASUAL),
    ("interview", "interview", Style.FORMAL),
    ("wedding", "wedding", Style.FORMAL),
    ("date", "date night", Style.SMART_CASUAL),
    ("dinner", "dinner", Style.SMART_CASUAL),
    ("party", "party", Style.STREETWEAR),
    ("gym", "gym", Style.SPORTY),
    ("workout", "workout", Style.SPORTY),
    ("travel", "travel", Style.CASUAL),
    ("casual", "casual outing", Style.CASUAL),
    ("formal", "formal event", Style.FORMAL),
]

_NO_SHOPPING_PHRASES = ["no shopping", "don't show products", "do not show products", "no products", "no links"]


def heuristic_intent(text: str) -> StyleIntent:
    """Deterministic keyword/regex intent parse — the keyless fallback."""
    lowered = text.lower()

    budget: float | None = None
    budget_match = _BUDGET_RE.search(lowered)
    if budget_match:
        try:
            budget = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            budget = None

    climate = next(
        (label for label, words in _CLIMATE_KEYWORDS.items() if any(w in lowered for w in words)),
        None,
    )

    occasion: str | None = None
    preferred_styles: list[Style] = []
    for keyword, label, style in _OCCASION_KEYWORDS:
        if keyword in lowered:
            occasion = occasion or label
            if style not in preferred_styles:
                preferred_styles.append(style)

    # Direct style-taxonomy mentions win over occasion leanings.
    for style in Style:
        if style == Style.OTHER:
            continue
        if style.value.replace("_", " ") in lowered or style.value in lowered:
            if style in preferred_styles:
                preferred_styles.remove(style)
            preferred_styles.insert(0, style)

    wants_shopping = not any(phrase in lowered for phrase in _NO_SHOPPING_PHRASES)

    return StyleIntent(
        occasion=occasion,
        budget_total_inr=budget,
        climate=climate,
        preferred_styles=preferred_styles,
        wants_shopping=wants_shopping,
    ).normalized()


class IntentAgent(BaseAgent):
    """Parses ``ctx.metadata['user_intent_text']`` into a validated StyleIntent."""

    name = "intent"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        super().__init__()
        self._llm = llm_service

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        text = (ctx.metadata.get("user_intent_text") or "").strip()
        if not text:
            ctx.metadata["intent"] = None
            return ctx

        intent: StyleIntent
        source = "heuristic"
        if self._llm is not None and self._llm.enabled:
            try:
                intent = await self._llm.extract_intent(text)
                source = "llm"
            except LLMError as exc:
                logger.warning("intent_extraction_failed", error=str(exc))
                intent = heuristic_intent(text)
        else:
            intent = heuristic_intent(text)

        ctx.metadata["intent"] = intent.model_dump(mode="json")
        ctx.metadata["intent_source"] = source

        logger.info(
            "intent_parsed",
            source=source,
            occasion=intent.occasion,
            budget=intent.budget_total_inr,
            preferred_styles=[s.value for s in intent.preferred_styles],
            wants_shopping=intent.wants_shopping,
        )
        return ctx


def intent_from_context(ctx: AgentContext) -> StyleIntent | None:
    """Typed accessor for the parsed intent stored in context metadata."""
    raw = ctx.metadata.get("intent")
    if not raw:
        return None
    return StyleIntent.model_validate(raw)
