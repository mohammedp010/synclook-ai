"""Structured user-intent and verifier schemas.

``StyleIntent`` is the contract between the LLM extraction step and the
deterministic pipeline: the LLM *proposes* a structured interpretation of the
user's free-text request, and ``normalized()`` applies deterministic
validation before anything downstream may consume it. The rule engine — not
the LLM — remains the authority on what an outfit may contain.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.clothing import Style

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
            and self.budget_total_inr is None
            and self.climate is None
            and self.dress_code is None
            and not self.preferred_styles
            and not self.avoid_items
            and not self.owned_items
            and self.wants_shopping
        )


IssueCode = Literal[
    "incomplete_outfit",
    "forbidden_item",
    "duplicate_item",
    "budget_exceeded",
    "occasion_mismatch",
    "unsupported_claim",
]

# Issues the retry loop can act on by tightening constraints and rebuilding.
FIXABLE_ISSUE_CODES: set[str] = {"forbidden_item", "duplicate_item", "unsupported_claim"}


class RecommendationIssue(BaseModel):
    """One problem the verifier found in a recommendation."""

    recommendation_index: int = Field(ge=0, description="Index into the recommendations list.")
    code: IssueCode
    detail: str = Field(description="Human-readable description of the problem.")
    item_type: str | None = Field(
        default=None,
        description="Offending item type, when the issue concerns a specific item.",
    )

    @property
    def fixable(self) -> bool:
        return self.code in FIXABLE_ISSUE_CODES
