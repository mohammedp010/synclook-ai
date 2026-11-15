"""Pydantic schemas for API requests and responses."""

import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.clothing import Color
from backend.schemas.perception import GarmentTags, Warmth
from backend.schemas.taxonomy import (
    GARMENT_TYPE_OPTIONS,
    ColorName,
    Formality,
    GarmentCategory,
    GarmentType,
    Occasion,
    PatternName,
)


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
        description="Product gate relevance: the product of the three Jev probabilities",
    )
    match_reason: str = Field(
        default="",
        description="Short explanation of why this product matched",
    )
    match_evidence: list[str] = Field(
        default_factory=list,
        description="The product gate's facts behind this product, one per line (Jev item, colour, buyer)",
    )


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = "healthy"
    version: str


# ──────────────────────────────────────────────────────────────────────
#  Closet and outfits (Phase 3)
# ──────────────────────────────────────────────────────────────────────


class ClosetItemOut(GarmentTags):
    id: UUID
    image_url: str = Field(description="GET this for the stored 512 px JPEG")


class ClosetItemPatch(BaseModel):
    """A user's correction to one or more tags. Category and colour family follow in code."""

    model_config = ConfigDict(extra="forbid")

    garment_type: str | None = Field(default=None, description="A GarmentType or AccessoryType value, or 'other'")
    color: ColorName | None = None
    secondary_color: ColorName | None = None
    pattern: PatternName | None = None
    formality: Formality | None = None
    warmth: Warmth | None = None
    occasions: list[Occasion] | None = None
    short_label: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("garment_type")
    @classmethod
    def _known_type(cls, value: str | None) -> str | None:
        if value is not None and value not in GARMENT_TYPE_OPTIONS:
            raise ValueError("unknown garment_type")
        return value


class DemoClosetOut(BaseModel):
    added: int
    total: int


class McpKeyOut(BaseModel):
    url: str = Field(description="This closet's private MCP endpoint; add it to Claude or ChatGPT as a connector")


class WearRequest(BaseModel):
    item_ids: list[UUID] = Field(min_length=1, max_length=12, description="Items in this closet, e.g. one outfit")
    action: Literal["worn", "saved", "skipped"]
    occasion: Occasion | None = None
    date: dt.date | None = Field(default=None, description="Day it happened; today when omitted, never in the future")


class WearOut(WearRequest):
    id: UUID
    date: dt.date


class ItemWearOut(BaseModel):
    id: UUID
    short_label: str
    times_worn: int
    last_worn: dt.date | None


class ClosetStatsOut(BaseModel):
    items: list[ItemWearOut] = Field(description="Every closet item, most worn first")
    never_worn: list[UUID]


class OutfitsRequest(BaseModel):
    occasion: str = Field(
        min_length=1,
        max_length=300,
        description="An Occasion value (no model call), or free text such as 'dinner with my in-laws' (one call)",
    )
    place: str | None = Field(default=None, max_length=120, description="City for the weather, e.g. 'Mumbai'")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    date: dt.date | None = Field(default=None, description="Day to dress for; today when omitted")


class WeatherOut(BaseModel):
    temperature_c: float
    band: str
    rain: bool


class OutfitPiece(BaseModel):
    id: UUID
    short_label: str
    garment_type: str
    category: GarmentCategory
    image_url: str


class OutfitOut(BaseModel):
    items: list[OutfitPiece]
    score: float = Field(description="Rule score: the sum of score_parts. A ranking number, not a probability")
    score_parts: dict[str, float]
    evidence: list[str] = Field(description="Rule facts; the explanation may only use these")
    explanation: str
    explanation_source: Literal["model", "template"]


class OutfitsResponse(BaseModel):
    occasion: Occasion
    occasion_from_text: bool = Field(description="True when the text model read the occasion from free text")
    weather: WeatherOut | None
    outfits: list[OutfitOut]
    reason: str | None = Field(description="Why there are fewer than 3 outfits")
    notes: list[str]


# ──────────────────────────────────────────────────────────────────────
#  What one thing should I buy? (Phase 4)
# ──────────────────────────────────────────────────────────────────────

Buyer = Literal["menswear", "womenswear", "all"]


class GapsRequest(BaseModel):
    buyer: Buyer = Field(default="all", description="menswear leaves out dresses, skirts and blouses")


class GapPiece(BaseModel):
    id: UUID | None = Field(description="None for the item to buy")
    short_label: str
    garment_type: str
    category: GarmentCategory
    image_url: str | None


class GapOut(BaseModel):
    garment_type: GarmentType
    color: Color = Field(description="Colour family; send both to POST /shop/search")
    label: str
    new_outfits: int = Field(description="Valid outfits it adds across all occasions, each counted once")
    new_outfits_by_occasion: dict[Occasion, int]
    occasions_unlocked: list[Occasion] = Field(description="Occasions the closet had no outfit for")
    example_occasion: Occasion
    example: list[GapPiece]
    example_evidence: list[str]


class GapsResponse(BaseModel):
    gaps: list[GapOut]
    candidates_checked: int
    reason: str | None = Field(description="Why there are fewer than 3 suggestions")


class ShopSearchRequest(BaseModel):
    garment_type: GarmentType
    color: Color
    buyer: Buyer = "all"
    max_price: int | None = Field(default=None, ge=1, description="Budget in ₹; listings over it are dropped")


class ShopSearchResponse(BaseModel):
    query: str
    checked: int = Field(description="Listings the product gate looked at")
    products: list[ProductLink] = Field(description="Only listings that passed the gate, best first")
    note: str | None = Field(description="Why there are no products, when there are none")
