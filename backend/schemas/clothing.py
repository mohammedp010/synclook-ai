"""Pydantic schemas for clothing attributes and vision output."""

from enum import Enum

from pydantic import BaseModel, Field

from backend.schemas.taxonomy import Aesthetic, ColorName, Formality, Occasion


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
    # Pixel-derived colour detail (Phase 1). ``primary_color`` stays the coarse
    # live enum the styling rules key on; these carry what the pixels add.
    color_name: ColorName | None = Field(
        default=None, description="Fine colour name (e.g. charcoal vs grey) from the target taxonomy"
    )
    primary_hex: str | None = Field(default=None, description="Measured hex of the primary colour")
    secondary_hex: str | None = Field(default=None, description="Measured hex of the secondary colour")
    # Fine garment type from the full-taxonomy head — a GarmentType or
    # AccessoryType value ("denim_jacket", "loafers", "belt"). clothing_type
    # stays the coarse enum the style rules key on.
    garment_type: str | None = Field(default=None, description="Fine garment or accessory type")
    garment_type_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Judged from the VLM description (perception_mode="cascade" with a VLM).
    # Separate from ``style`` on purpose: Style mixes register and aesthetic on
    # one axis, and re-mapping it would change styling rules no eval covers yet.
    formality: Formality | None = Field(default=None, description="0 lounge … 4 black tie")
    aesthetic: Aesthetic | None = Field(
        default=None, description="Visual register, e.g. minimalist, ethnic_traditional"
    )
    # Upload guard verdict for photos that were allowed through ("pass" or
    # "degrade"); "retake" and "reject" never get this far — they are a 422.
    guard: str = Field(default="pass", description="pass | degrade")
    guard_reason: str = Field(default="ok", description="e.g. ok, uncertain_subject, multiple_garments")
    guard_message: str = Field(default="", description="A note for the user when guard is 'degrade'")
    other_garments: list[str] = Field(
        default_factory=list, description="Other items visible in the photo, as the VLM named them"
    )
    # Occasion fit from the Jev judge (perception_mode="cascade"). Empty on the
    # CLIP path or when Jev is unavailable — never a guess.
    occasions: list[Occasion] = Field(
        default_factory=list, description="Occasions this garment suits, most probable first"
    )
    occasion_scores: dict[Occasion, float] = Field(
        default_factory=dict, description="Calibrated probability of fit for every occasion"
    )
