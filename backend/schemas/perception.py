"""What one garment photo becomes: the validated tags a closet item is stored with."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.schemas.taxonomy import ColorName, Formality, GarmentCategory, Occasion, PatternName


class Warmth(str, Enum):
    """How warm the garment is to wear — the weather filter's input (Phase 3)."""

    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class GarmentTags(BaseModel):
    """Every field is clamped to the taxonomy by ``services.perception``; none is a raw model string."""

    garment_type: str = Field(description="A GarmentType or AccessoryType value, or 'other'")
    category: GarmentCategory = Field(description="Derived from garment_type in code, never asked of the model")
    color: ColorName = Field(description="The model's colour word picks the family; the pixels pick the shade")
    color_family: str = Field(description="The coarse family, COARSE_COLOR[color]")
    color_hex: str = Field(description="Measured from the pixels")
    secondary_color: ColorName | None = None
    pattern: PatternName = PatternName.SOLID
    formality: Formality = Formality.CASUAL
    warmth: Warmth = Warmth.MEDIUM
    occasions: list[Occasion] = Field(default_factory=list)
    short_label: str = Field(description="A few words for the closet list, e.g. 'navy linen shirt'")
    item_count: int = Field(default=1, ge=1, description="Garments the model saw; >1 means the photo shows an outfit")
