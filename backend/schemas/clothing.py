"""Pydantic schemas for clothing attributes and vision output."""

from enum import Enum

from pydantic import BaseModel, Field


class ClothingType(str, Enum):
    TSHIRT = "t-shirt"
    SHIRT = "shirt"
    BLOUSE = "blouse"
    JACKET = "jacket"
    BLAZER = "blazer"
    COAT = "coat"
    SWEATER = "sweater"
    HOODIE = "hoodie"
    DRESS = "dress"
    SKIRT = "skirt"
    TROUSERS = "trousers"
    JEANS = "jeans"
    SHORTS = "shorts"
    CHINOS = "chinos"
    SUIT = "suit"
    SHOES = "shoes"
    ACCESSORY = "accessory"
    OTHER = "other"


class Color(str, Enum):
    BLACK = "black"
    WHITE = "white"
    RED = "red"
    BLUE = "blue"
    NAVY = "navy"
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    PINK = "pink"
    PURPLE = "purple"
    BROWN = "brown"
    GREY = "grey"
    BEIGE = "beige"
    CREAM = "cream"
    MAROON = "maroon"
    OLIVE = "olive"
    TEAL = "teal"
    OTHER = "other"


class Pattern(str, Enum):
    SOLID = "solid"
    STRIPED = "striped"
    CHECKERED = "checkered"
    FLORAL = "floral"
    POLKA_DOT = "polka_dot"
    PLAID = "plaid"
    ABSTRACT = "abstract"
    OTHER = "other"


class Style(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    SMART_CASUAL = "smart_casual"
    STREETWEAR = "streetwear"
    SPORTY = "sporty"
    BOHEMIAN = "bohemian"
    MINIMALIST = "minimalist"
    OTHER = "other"


class ClothingAttributes(BaseModel):
    """Structured output from the Vision Agent."""

    clothing_type: ClothingType
    primary_color: Color
    secondary_color: Color | None = None
    pattern: Pattern = Pattern.SOLID
    style: Style
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence of the clothing-type detection (primary signal)")
    color_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence of the color detection")
    pattern_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence of the pattern detection")
    style_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence of the style detection")
    description: str = Field(default="", description="Free-text description from BLIP captioning")
    description_relevant: bool = Field(
        default=True,
        description="Whether caption appears relevant to the detected clothing item.",
    )
