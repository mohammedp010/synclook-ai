"""LLM Service — DeepSeek integration for the reasoning layer of the pipeline.

Three capabilities, all constrained by deterministic validation downstream:

- ``extract_intent``: free-text request → structured ``StyleIntent``
  (LangChain structured output over DeepSeek's OpenAI-compatible API)
- ``generate_grounded_explanation``: writes the outfit explanation strictly
  from rule-engine evidence — the LLM words the reasoning, it does not
  choose outfit items
- ``critique_recommendations``: structured critic pass returning
  ``RecommendationIssue`` objects for the verifier

Falls back gracefully when ``DEEPSEEK_API_KEY`` is unset: callers must treat
``enabled=False`` as "use deterministic behavior".
"""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field, SecretStr

from backend.core.config import Settings, get_settings
from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.core.tracing import get_tracer
from backend.schemas.intent import RecommendationIssue, StyleIntent

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  Prompts
# ──────────────────────────────────────────────────────────────────────

_INTENT_SYSTEM_PROMPT = (
    "You extract structured styling constraints from a user's request about an outfit. "
    "Map any style words to the catalog taxonomy: formal, casual, smart_casual, streetwear, "
    "sporty, bohemian, minimalist. Budgets are in INR unless another currency is explicit "
    "(convert roughly if needed). Only extract what the user actually said — never invent "
    "constraints they did not express."
)

_EXPLANATION_SYSTEM_PROMPT = (
    "You are a professional fashion stylist. Write a warm 2-3 sentence explanation of an "
    "outfit recommendation using ONLY the facts provided. Never mention clothing items, "
    "colors, or styles that are not in the facts. No markdown, under 80 words."
)

_CRITIC_SYSTEM_PROMPT = (
    "You are a strict fashion-recommendation reviewer. Given the detected garment, the user's "
    "intent, and the proposed outfits, report concrete problems only — occasion mismatches and "
    "explanation claims unsupported by the outfit facts. If there are no real problems, return "
    "an empty issue list. Never invent problems."
)


class _CritiqueResult(BaseModel):
    """Container so the critic's structured output is a single object."""

    issues: list[RecommendationIssue] = Field(default_factory=list)


class LLMService:
    """Async DeepSeek wrapper for intent extraction, grounded explanations, and critique.

    Falls back gracefully if the API key is missing, the service is
    unavailable, or rate limits are hit.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._enabled = bool(self._settings.deepseek_api_key)
        self._structured: ChatOpenAI | None = None

        if self._enabled:
            self._client = AsyncOpenAI(
                api_key=self._settings.deepseek_api_key,
                base_url=self._settings.deepseek_base_url,
            )
        else:
            self._client = None  # type: ignore[assignment]
            logger.warning("llm_disabled", reason="DEEPSEEK_API_KEY not set")

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Low-level helpers ─────────────────────────────────────────────

    def _structured_model(self) -> ChatOpenAI:
        """Lazily build the LangChain client used for structured outputs."""
        if self._structured is None:
            self._structured = ChatOpenAI(
                api_key=SecretStr(self._settings.deepseek_api_key),
                base_url=self._settings.deepseek_base_url,
                model=self._settings.deepseek_model,
                temperature=0.0,  # deterministic extraction/critique
                timeout=30,
                max_retries=1,
            )
        return self._structured

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the text response."""
        if not self._enabled:
            raise LLMError("LLM service is disabled (no API key)")

        try:
            with get_tracer().generation(
                "deepseek.chat",
                model=self._settings.deepseek_model,
                input=user_prompt,
            ) as generation:
                response = await self._client.chat.completions.create(
                    model=self._settings.deepseek_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self._settings.llm_temperature,
                    max_tokens=self._settings.llm_max_tokens,
                )
                content = (response.choices[0].message.content or "").strip()
                if generation is not None:
                    usage = getattr(response, "usage", None)
                    generation.update(
                        output=content,
                        usage_details=(
                            {"input": usage.prompt_tokens, "output": usage.completion_tokens} if usage else None
                        ),
                    )
                return content
        except (APIConnectionError, RateLimitError, APIError) as exc:
            logger.warning("llm_api_error", error=str(exc))
            raise LLMError(f"DeepSeek API error: {exc}") from exc

    async def _structured_call[T: BaseModel](self, schema: type[T], system_prompt: str, user_prompt: str) -> T:
        """Run a structured-output call (function calling under the hood)."""
        if not self._enabled:
            raise LLMError("LLM service is disabled (no API key)")

        # DeepSeek supports tool/function calling but not OpenAI's strict
        # json_schema response format, so pin the method explicitly.
        model = self._structured_model().with_structured_output(schema, method="function_calling")
        try:
            with get_tracer().generation(
                f"deepseek.structured.{schema.__name__}",
                model=self._settings.deepseek_model,
                input=user_prompt,
            ) as generation:
                result = await model.ainvoke(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ]
                )
                if not isinstance(result, schema):
                    raise LLMError(f"Structured output returned {type(result).__name__}, expected {schema.__name__}")
                if generation is not None:
                    generation.update(output=result.model_dump(mode="json"))
                return result
        except LLMError:
            raise
        except Exception as exc:  # langchain wraps provider errors variously
            logger.warning("llm_structured_error", schema=schema.__name__, error=str(exc))
            raise LLMError(f"DeepSeek structured call failed: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────

    async def extract_intent(self, user_text: str) -> StyleIntent:
        """Parse a free-text styling request into a validated StyleIntent."""
        result = await self._structured_call(
            StyleIntent,
            _INTENT_SYSTEM_PROMPT,
            f"User request: {user_text.strip()}",
        )
        return result.normalized()

    async def generate_grounded_explanation(
        self,
        *,
        facts: list[str],
        occasion: str | None = None,
    ) -> str:
        """Write an outfit explanation strictly from rule-engine evidence."""
        lines = "\n".join(f"- {fact}" for fact in facts)
        occasion_line = f"\nThe user is dressing for: {occasion}." if occasion else ""
        prompt = f"Facts about this outfit:\n{lines}{occasion_line}\n\nWrite the explanation."
        return await self._chat(_EXPLANATION_SYSTEM_PROMPT, prompt)

    async def critique_recommendations(
        self,
        *,
        detected: str,
        intent_summary: str,
        outfits: list[dict[str, Any]],
    ) -> list[RecommendationIssue]:
        """Structured critic pass over the assembled recommendations."""
        payload = json.dumps(outfits, ensure_ascii=False)
        prompt = (
            f"Detected garment: {detected}\n"
            f"User intent: {intent_summary or 'none stated'}\n"
            f"Proposed outfits (JSON): {payload}\n\n"
            "Report issues with codes 'occasion_mismatch' or 'unsupported_claim' only."
        )
        result = await self._structured_call(_CritiqueResult, _CRITIC_SYSTEM_PROMPT, prompt)
        return result.issues
