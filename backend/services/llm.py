"""LLM Service — the text model, over OpenRouter (one key with the vision model).

Capabilities, all constrained by deterministic validation downstream:

- ``extract_intent``: free-text request → structured ``StyleIntent``
  (one ``json_schema`` response)
- ``generate_grounded_explanation``: writes the outfit explanation strictly
  from rule-engine evidence — the LLM words the reasoning, it does not
  choose outfit items
- ``structured``: the same parse for callers' own schemas

Every call raises ``LLMError`` when ``VLM_API_KEY`` (the OpenRouter key) is unset.
"""

from __future__ import annotations

from typing import Any, cast

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ValidationError

from backend.core.config import Settings, get_settings
from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.core.tracing import get_tracer
from backend.schemas.intent import StyleIntent
from backend.schemas.taxonomy import OCCASION_DESCRIPTIONS

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────
#  Prompts
# ──────────────────────────────────────────────────────────────────────

_INTENT_SYSTEM_PROMPT = (
    "You extract structured styling constraints from a user's request about an outfit. "
    "Map any style words to the catalog taxonomy: formal, casual, smart_casual, streetwear, "
    "sporty, bohemian, minimalist. Budgets are in INR unless another currency is explicit "
    "(convert roughly if needed). Only extract what the user actually said — never invent "
    "constraints they did not express. occasion_type is one of these, or null if none is named:\n"
    + "\n".join(f"- {occ.value}: {desc}" for occ, desc in OCCASION_DESCRIPTIONS.items())
)

_EXPLANATION_SYSTEM_PROMPT = (
    "You are a professional fashion stylist. Write a warm 2-3 sentence explanation of an "
    "outfit recommendation using ONLY the facts provided. Never mention clothing items, "
    "colors, or styles that are not in the facts. No markdown, under 80 words."
)


class LLMService:
    """Async text-model client for intent extraction and grounded explanations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._enabled = bool(self._settings.vlm_api_key)

        if self._enabled:
            self._client = AsyncOpenAI(
                api_key=self._settings.vlm_api_key,
                base_url=self._settings.vlm_base_url,
            )
        else:
            self._client = None  # type: ignore[assignment]
            logger.warning("llm_disabled", reason="VLM_API_KEY not set")

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Low-level helpers ─────────────────────────────────────────────

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return the text response."""
        if not self._enabled:
            raise LLMError("LLM service is disabled (no API key)")

        try:
            with get_tracer().generation(
                "llm.chat",
                model=self._settings.text_model,
                input=user_prompt,
            ) as generation:
                response = await self._client.chat.completions.create(
                    model=self._settings.text_model,
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
            raise LLMError(f"LLM API error: {exc}") from exc

    async def _structured_call[T: BaseModel](self, schema: type[T], system_prompt: str, user_prompt: str) -> T:
        """One ``json_schema`` response, validated against ``schema`` in code.

        Not a forced tool call: Gemini on OpenRouter ended about 1 in 12 forced
        calls with ``finish_reason=error`` and no call, while ``json_schema``
        parsed 20 of 20 (2026-11-15). ``strict`` is off because Pydantic schemas
        with defaults are not strict-mode schemas; validation happens here.
        """
        if not self._enabled:
            raise LLMError("LLM service is disabled (no API key)")

        name = schema.__name__
        try:
            with get_tracer().generation(
                f"llm.structured.{name}",
                model=self._settings.text_model,
                input=user_prompt,
            ) as generation:
                response = await self._client.chat.completions.create(
                    model=self._settings.text_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": name, "strict": False, "schema": schema.model_json_schema()},
                    },
                    # Only providers that honour response_format.
                    extra_body={"provider": {"require_parameters": True}},
                    temperature=0.0,  # deterministic extraction
                    timeout=30,
                )
                content = response.choices[0].message.content if response.choices else None
                if not content:
                    raise LLMError(f"Structured call returned no {name}")
                result = schema.model_validate_json(content)
                if generation is not None:
                    generation.update(output=result.model_dump(mode="json"))
                return result
        except (APIConnectionError, RateLimitError, APIError) as exc:
            logger.warning("llm_structured_error", schema=name, error=str(exc))
            raise LLMError(f"LLM structured call failed: {exc}") from exc
        except ValidationError as exc:
            logger.warning("llm_structured_invalid", schema=name, error=str(exc))
            raise LLMError(f"LLM returned an invalid {name}: {exc}") from exc

    # ── Public API ────────────────────────────────────────────────────

    async def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, max_tokens: int
    ) -> ChatCompletion:
        """One chat step on ``agent_model`` with tools offered (``tool_choice`` auto); the agent drives the loop."""
        if not self._enabled:
            raise LLMError("LLM service is disabled (no API key)")
        try:
            return await self._client.chat.completions.create(
                model=self._settings.agent_model,
                messages=cast(Any, messages),
                tools=cast(Any, tools),
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=30,
            )
        except (APIConnectionError, RateLimitError, APIError) as exc:
            logger.warning("llm_tools_error", error=str(exc))
            raise LLMError(f"LLM tool call failed: {exc}") from exc

    async def structured[T: BaseModel](self, schema: type[T], *, system_prompt: str, user_prompt: str) -> T:
        """Public structured-output call for callers with their own prompts (e.g. eval judges)."""
        return await self._structured_call(schema, system_prompt, user_prompt)

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
