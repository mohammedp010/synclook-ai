"""Pydantic schemas for API requests and responses."""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from backend.schemas.clothing import ClothingAttributes


class FeedbackType(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class Gender(str, Enum):
    """Legacy search preference kept for backwards-compatible API clients."""

    MALE = "male"
    FEMALE = "female"
    UNISEX = "unisex"


class ShoppingIntent(str, Enum):
    MENSWEAR = "menswear"
    WOMENSWEAR = "womenswear"
    UNISEX = "unisex"
    ALL = "all"


class ProductLink(BaseModel):
    """A product from an online store."""

    title: str
    price: str
    link: str = Field(description="URL to purchase the product")
    thumbnail: str = Field(description="Product image URL")
    source: str = Field(description="Store name, e.g. Amazon.in, Myntra")
    match_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Product relevance score for the recommendation item",
    )
    match_reason: str = Field(
        default="",
        description="Short explanation of why this product matched",
    )


class RecommendationItem(BaseModel):
    """A single outfit recommendation."""

    item_type: str
    color: str
    style: str
    reason: str = Field(description="Why this item was recommended")
    products: list[ProductLink] = Field(
        default_factory=list,
        description="Matching products from online stores",
    )


class Recommendation(BaseModel):
    """Full recommendation output from the Recommendation Agent."""

    id: UUID = Field(default_factory=uuid4)
    items: list[RecommendationItem]
    overall_explanation: str = Field(
        description="Rule-generated outfit explanation, optionally tone-refined by the LLM"
    )
    style_tags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)


class AnalysisRequest(BaseModel):
    """Request schema — metadata only; image sent as multipart."""

    user_id: str | None = None


class AnalysisResponse(BaseModel):
    """Full response for a clothing analysis + recommendation request."""

    request_id: UUID = Field(default_factory=uuid4)
    detected_attributes: ClothingAttributes
    recommendations: list[Recommendation]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FeedbackRequest(BaseModel):
    """User feedback on a recommendation."""

    request_id: UUID
    recommendation_id: UUID
    feedback: FeedbackType
    user_id: str | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Acknowledgement of stored feedback."""

    status: str = "ok"
    message: str = "Feedback recorded"


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "healthy"
    version: str
