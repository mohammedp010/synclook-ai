"""Structured user-intent and verifier schemas.

``StyleIntent`` is the contract between the LLM extraction step and the
deterministic pipeline: the LLM *proposes* a structured interpretation of the
user's free-text request, and ``normalized()`` applies deterministic
validation before anything downstream may consume it. The rule engine — not
the LLM — remains the authority on what an outfit may contain.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.schemas.clothing import Style
from backend.schemas.taxonomy import Occasion

# Caps applied during normalization so a runaway extraction can't flood
# downstream prompts or filters.
_MAX_LIST_ITEMS = 8
_MAX_TEXT_LEN = 120


class StyleIntent(BaseModel):
    """Structured interpretation of the user's free-text styling request."""

    occasion: str | None = Field(
        default=None,
        description="Event or setting the outfit is for, e.g. 'office party', 'rainy dinner', 'wedding'.",
    )
    # The rules key on this, not on the words above. The extraction call fills
    # both; an occasion outside the taxonomy becomes None in code, not an error.
    occasion_type: Occasion | None = Field(
        default=None,
        description="The one listed occasion the request names, or null if it names none of them.",
    )
    budget_total_inr: float | None = Field(
        default=None,
        description="Total outfit budget in INR if the user mentioned one.",
    )
    climate: str | None = Field(
        default=None,
        description="Weather/climate constraint, e.g. 'rainy', 'hot', 'cold'.",
    )
    dress_code: str | None = Field(
        default=None,
        description="Explicit dress code, e.g. 'office-safe', 'black tie'.",
    )
    preferred_styles: list[Style] = Field(
        default_factory=list,
        description="Target styles implied by the request, mapped to the catalog's style taxonomy.",
    )
    avoid_items: list[str] = Field(
        default_factory=list,
        description="Item types or garments the user wants excluded.",
    )
    owned_items: list[str] = Field(
        default_factory=list,
        description="Garments the user already owns and wants incorporated.",
    )
    wants_shopping: bool = Field(
        default=True,
        description="False if the user explicitly does not want product links.",
    )

    @field_validator("occasion_type", mode="before")
    @classmethod
    def _known_occasion(cls, value: Any) -> Any:
        return value if value is None or isinstance(value, Occasion) or value in Occasion._value2member_map_ else None

    def normalized(self) -> StyleIntent:
        """Deterministic validation: clamp, dedupe, and truncate LLM output."""

        def clean_list(values: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for value in values:
                v = value.strip().lower()[:_MAX_TEXT_LEN]
                if v and v not in seen:
                    seen.add(v)
                    out.append(v)
            return out[:_MAX_LIST_ITEMS]

        budget = self.budget_total_inr
        if budget is not None and budget <= 0:
            budget = None

        return StyleIntent(
            occasion=(self.occasion or "").strip()[:_MAX_TEXT_LEN] or None,
            occasion_type=self.occasion_type,
            budget_total_inr=budget,
            climate=(self.climate or "").strip().lower()[:_MAX_TEXT_LEN] or None,
            dress_code=(self.dress_code or "").strip()[:_MAX_TEXT_LEN] or None,
            preferred_styles=list(dict.fromkeys(self.preferred_styles))[:3],
            avoid_items=clean_list(self.avoid_items),
            owned_items=clean_list(self.owned_items),
            wants_shopping=self.wants_shopping,
        )

    @property
    def is_empty(self) -> bool:
        """True when the intent adds no constraints beyond defaults."""
        return (
            self.occasion is None
            and self.occasion_type is None
            and self.budget_total_inr is None
            and self.climate is None
            and self.dress_code is None
            and not self.preferred_styles
            and not self.avoid_items
            and not self.owned_items
            and self.wants_shopping
        )
