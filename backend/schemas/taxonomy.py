"""Target perception taxonomy — the vocabulary Phase 2 will classify into.

This module is **data, not behaviour**. Nothing in the running pipeline imports
it yet: the live path still speaks the smaller ``schemas.clothing`` enums. It
lands ahead of the pipeline because the Phase 0 eval set is labeled against it,
and a label set written against today's 18-member ``ClothingType`` would have
to be relabeled by hand the moment the taxonomy grows.

Three design decisions worth keeping:

1. **Occasion is not style.** ``schemas.clothing.Style`` mixes an occasion
   register (``formal``) with aesthetics (``minimalist``, ``streetwear``) and
   forces a single winner across both. Here they are separate axes: an
   ``Occasion`` set (multi-label), a ``Formality`` ladder (ordered), and an
   ``Aesthetic`` (single-label).
2. **Occasion is multi-label.** A navy blazer is honestly right for
   ``business_formal`` *and* ``smart_casual`` *and* ``wedding_guest``. Anything
   that forces one answer is wrong about the garment, not decisive about it.
3. **Indian-market garments are first class.** Prices are in ₹ and
   ``shopping_country="in"``; a taxonomy that cannot name a kurta cannot serve
   the catalog it shops from.

``COARSE_TYPE`` maps every fine-grained garment back onto the live enum, so the
current CLIP pipeline can be scored against these labels without pretending it
had access to distinctions it was never given.
"""

from __future__ import annotations

from enum import Enum


class GarmentCategory(str, Enum):
    """Where on the body a garment is worn.

    The one distinction CLIP makes reliably in a photograph — ingestion already
    leans on it because the model reads a real blazer as ``blouse`` at 0.39.
    """

    TOPWEAR = "topwear"
    OUTERWEAR = "outerwear"
    BOTTOMWEAR = "bottomwear"
    FULLBODY = "fullbody"
    FOOTWEAR = "footwear"
    ACCESSORY = "accessory"
    OTHER = "other"


class GarmentType(str, Enum):
    """Fine-grained garment vocabulary (~60 members, well inside Jev's 255)."""

    # Topwear
    T_SHIRT = "t_shirt"
    POLO = "polo"
    SHIRT = "shirt"
    BLOUSE = "blouse"
    TANK_TOP = "tank_top"
    CROP_TOP = "crop_top"
    TUNIC = "tunic"
    KURTA = "kurta"
    SWEATSHIRT = "sweatshirt"
    HOODIE = "hoodie"
    SWEATER = "sweater"
    CARDIGAN = "cardigan"

    # Outerwear
    BLAZER = "blazer"
    JACKET = "jacket"
    DENIM_JACKET = "denim_jacket"
    LEATHER_JACKET = "leather_jacket"
    BOMBER = "bomber"
    COAT = "coat"
    TRENCH_COAT = "trench_coat"
    PUFFER = "puffer"
    OVERSHIRT = "overshirt"
    WAISTCOAT = "waistcoat"
    NEHRU_JACKET = "nehru_jacket"
    SHERWANI = "sherwani"

    # Bottomwear
    TROUSERS = "trousers"
    JEANS = "jeans"
    CHINOS = "chinos"
    SHORTS = "shorts"
    CARGO_PANTS = "cargo_pants"
    JOGGERS = "joggers"
    TRACK_PANTS = "track_pants"
    SKIRT = "skirt"
    LEGGINGS = "leggings"
    PALAZZO = "palazzo"
    DHOTI = "dhoti"

    # Full body
    DRESS = "dress"
    GOWN = "gown"
    JUMPSUIT = "jumpsuit"
    ROMPER = "romper"
    SUIT = "suit"
    CO_ORD_SET = "co_ord_set"
    SAREE = "saree"
    LEHENGA = "lehenga"
    ANARKALI = "anarkali"
    SALWAR_KAMEEZ = "salwar_kameez"

    # Footwear
    SNEAKERS = "sneakers"
    SPORTS_SHOES = "sports_shoes"
    FORMAL_SHOES = "formal_shoes"
    LOAFERS = "loafers"
    BOOTS = "boots"
    SANDALS = "sandals"
    HEELS = "heels"
    FLATS = "flats"
    FLIP_FLOPS = "flip_flops"
    JUTTIS = "juttis"

    OTHER = "other"


class AccessoryType(str, Enum):
    """Accessories, which today collapse into a single ``ACCESSORY`` member.

    That collapse is why accessory advice is unusable: the shopping agent ends
    up searching for the word "accessory". A belt and a clutch are not the same
    slot, do not pair with the same outfits, and are not the same query.
    """

    BELT = "belt"
    WATCH = "watch"
    TIE = "tie"
    BOW_TIE = "bow_tie"
    POCKET_SQUARE = "pocket_square"
    CUFFLINKS = "cufflinks"
    SCARF = "scarf"
    STOLE = "stole"
    DUPATTA = "dupatta"
    SUNGLASSES = "sunglasses"
    CAP = "cap"
    HAT = "hat"
    BEANIE = "beanie"
    NECKLACE = "necklace"
    EARRINGS = "earrings"
    BRACELET = "bracelet"
    RINGS = "rings"
    BROOCH = "brooch"
    TOTE_BAG = "tote_bag"
    BACKPACK = "backpack"
    CROSSBODY_BAG = "crossbody_bag"
    CLUTCH = "clutch"
    BRIEFCASE = "briefcase"
    SOCKS = "socks"
    OTHER = "other"


GARMENT_TYPE_OPTIONS: tuple[str, ...] = (
    *(g.value for g in GarmentType if g != GarmentType.OTHER),
    *(a.value for a in AccessoryType if a != AccessoryType.OTHER),
    "other",
)
"""Every garment and accessory name, with one ``other`` for both."""


class Occasion(str, Enum):
    """Where a garment can be worn. **Multi-label** — see module docstring."""

    BUSINESS_FORMAL = "business_formal"
    BUSINESS_CASUAL = "business_casual"
    SMART_CASUAL = "smart_casual"
    EVERYDAY_CASUAL = "everyday_casual"
    PARTY_NIGHT_OUT = "party_night_out"
    COCKTAIL_SEMI_FORMAL = "cocktail_semi_formal"
    WEDDING_GUEST = "wedding_guest"
    FESTIVE_ETHNIC = "festive_ethnic"
    BEACH_RESORT = "beach_resort"
    GYM_ATHLEISURE = "gym_athleisure"
    TRAVEL_COMMUTE = "travel_commute"
    DATE_NIGHT = "date_night"
    INTERVIEW = "interview"
    LOUNGEWEAR = "loungewear"


class Formality(int, Enum):
    """Ordered register ladder. The integer **is** the level, matching Jev's
    ``score`` semantics where a level's number is its array index."""

    LOUNGE = 0
    CASUAL = 1
    SMART_CASUAL = 2
    BUSINESS_FORMAL = 3
    BLACK_TIE = 4


FORMALITY_CRITERIA: list[str] = [
    "Worn at home only — pyjamas, house shorts, sleep tees",
    "Everyday out-of-house clothing — jeans, t-shirts, sneakers, casual dresses",
    "Neat and considered but not a suit — chinos with a shirt, a blazer over a tee, loafers",
    "Office-formal or a suit context — tailored trousers, dress shirts, blazers, formal leather shoes",
    "Black tie or heavy ceremonial dress — tuxedos, gowns, full sherwani or lehenga",
]
"""Ordered level descriptions for the Phase 2 Jev ``score`` question.

Deliberately descriptive: the reference documents bare numeric criteria
(``["0","1","2"]``) scoring 0.55 at confidence 0.33 where written levels scored
0.0 at confidence 1.0 on the same input. Levels describe *situations*, never
degrees — "moderately formal" gives the model nothing to match against.
"""


OCCASION_DESCRIPTIONS: dict[Occasion, str] = {
    Occasion.BUSINESS_FORMAL: "a formal office or corporate setting where suits and tailoring are expected",
    Occasion.BUSINESS_CASUAL: "an office day with a relaxed dress code — no suit needed, but no gym or beach clothes",
    Occasion.SMART_CASUAL: "a neat but relaxed outing such as a nice lunch, a gallery, or casual Friday",
    Occasion.EVERYDAY_CASUAL: "ordinary daily life — errands, college, meeting friends for coffee",
    Occasion.PARTY_NIGHT_OUT: "a club, house party or night out with friends",
    Occasion.COCKTAIL_SEMI_FORMAL: "an evening cocktail party or semi-formal reception",
    Occasion.WEDDING_GUEST: "attending a wedding or wedding reception as a guest",
    Occasion.FESTIVE_ETHNIC: (
        "a festival or traditional celebration such as Diwali, Eid or a puja, where ethnic wear is customary"
    ),
    Occasion.BEACH_RESORT: "a beach day or a warm-weather resort holiday",
    Occasion.GYM_ATHLEISURE: "a gym session, a run, yoga or sport",
    Occasion.TRAVEL_COMMUTE: "a long flight, train journey or daily commute where comfort and practicality matter",
    Occasion.DATE_NIGHT: "a dinner date or romantic evening out",
    Occasion.INTERVIEW: "a job interview",
    Occasion.LOUNGEWEAR: "relaxing at home",
}
"""Written contrastively — each has to separate its occasion from its
neighbours (business-casual vs smart-casual, party vs cocktail), because the
model sees only the text, never the enum name."""


class Aesthetic(str, Enum):
    """Visual register, independent of how formal or what occasion."""

    MINIMALIST = "minimalist"
    CLASSIC = "classic"
    STREETWEAR = "streetwear"
    SPORTY = "sporty"
    BOHEMIAN = "bohemian"
    PREPPY = "preppy"
    EDGY = "edgy"
    ROMANTIC = "romantic"
    ETHNIC_TRADITIONAL = "ethnic_traditional"
    OTHER = "other"


class ColorName(str, Enum):
    """Named colours, expanded past the live enum with the shades that
    actually fail today (charcoal vs black, tan vs brown, off-white vs white).

    Phase 1 resolves these from pixels via CIELAB + ΔE2000, so each member needs
    a reference point in colour space — see ``evaluation``/Phase 1 palette.
    """

    BLACK = "black"
    CHARCOAL = "charcoal"
    GREY = "grey"
    LIGHT_GREY = "light_grey"
    WHITE = "white"
    OFF_WHITE = "off_white"
    CREAM = "cream"
    BEIGE = "beige"
    TAN = "tan"
    KHAKI = "khaki"
    BROWN = "brown"
    CAMEL = "camel"
    RUST = "rust"
    MAROON = "maroon"
    BURGUNDY = "burgundy"
    RED = "red"
    CORAL = "coral"
    PINK = "pink"
    ORANGE = "orange"
    MUSTARD = "mustard"
    YELLOW = "yellow"
    OLIVE = "olive"
    GREEN = "green"
    MINT = "mint"
    TEAL = "teal"
    DENIM_BLUE = "denim_blue"
    BLUE = "blue"
    NAVY = "navy"
    LAVENDER = "lavender"
    PURPLE = "purple"
    MULTICOLOR = "multicolor"
    OTHER = "other"


class PatternName(str, Enum):
    """Surface pattern, expanded past the live ``Pattern`` enum."""

    SOLID = "solid"
    STRIPED = "striped"
    CHECKERED = "checkered"
    PLAID = "plaid"
    FLORAL = "floral"
    POLKA_DOT = "polka_dot"
    GEOMETRIC = "geometric"
    ANIMAL_PRINT = "animal_print"
    CAMOUFLAGE = "camouflage"
    TIE_DYE = "tie_dye"
    COLOR_BLOCK = "color_block"
    EMBROIDERED = "embroidered"
    GRAPHIC_PRINT = "graphic_print"
    ABSTRACT = "abstract"
    OTHER = "other"


# ──────────────────────────────────────────────────────────────────────
#  Structure
# ──────────────────────────────────────────────────────────────────────

TYPE_CATEGORY: dict[GarmentType, GarmentCategory] = {
    **{
        t: GarmentCategory.TOPWEAR
        for t in (
            GarmentType.T_SHIRT,
            GarmentType.POLO,
            GarmentType.SHIRT,
            GarmentType.BLOUSE,
            GarmentType.TANK_TOP,
            GarmentType.CROP_TOP,
            GarmentType.TUNIC,
            GarmentType.KURTA,
            GarmentType.SWEATSHIRT,
            GarmentType.HOODIE,
            GarmentType.SWEATER,
            GarmentType.CARDIGAN,
        )
    },
    **{
        t: GarmentCategory.OUTERWEAR
        for t in (
            GarmentType.BLAZER,
            GarmentType.JACKET,
            GarmentType.DENIM_JACKET,
            GarmentType.LEATHER_JACKET,
            GarmentType.BOMBER,
            GarmentType.COAT,
            GarmentType.TRENCH_COAT,
            GarmentType.PUFFER,
            GarmentType.OVERSHIRT,
            GarmentType.WAISTCOAT,
            GarmentType.NEHRU_JACKET,
            GarmentType.SHERWANI,
        )
    },
    **{
        t: GarmentCategory.BOTTOMWEAR
        for t in (
            GarmentType.TROUSERS,
            GarmentType.JEANS,
            GarmentType.CHINOS,
            GarmentType.SHORTS,
            GarmentType.CARGO_PANTS,
            GarmentType.JOGGERS,
            GarmentType.TRACK_PANTS,
            GarmentType.SKIRT,
            GarmentType.LEGGINGS,
            GarmentType.PALAZZO,
            GarmentType.DHOTI,
        )
    },
    **{
        t: GarmentCategory.FULLBODY
        for t in (
            GarmentType.DRESS,
            GarmentType.GOWN,
            GarmentType.JUMPSUIT,
            GarmentType.ROMPER,
            GarmentType.SUIT,
            GarmentType.CO_ORD_SET,
            GarmentType.SAREE,
            GarmentType.LEHENGA,
            GarmentType.ANARKALI,
            GarmentType.SALWAR_KAMEEZ,
        )
    },
    **{
        t: GarmentCategory.FOOTWEAR
        for t in (
            GarmentType.SNEAKERS,
            GarmentType.SPORTS_SHOES,
            GarmentType.FORMAL_SHOES,
            GarmentType.LOAFERS,
            GarmentType.BOOTS,
            GarmentType.SANDALS,
            GarmentType.HEELS,
            GarmentType.FLATS,
            GarmentType.FLIP_FLOPS,
            GarmentType.JUTTIS,
        )
    },
    GarmentType.OTHER: GarmentCategory.OTHER,
}


# ──────────────────────────────────────────────────────────────────────
#  Bridges back to the live enums (so the baseline can be scored fairly)
# ──────────────────────────────────────────────────────────────────────

COARSE_TYPE: dict[GarmentType, str] = {
    GarmentType.T_SHIRT: "t-shirt",
    GarmentType.POLO: "t-shirt",
    GarmentType.TANK_TOP: "t-shirt",
    GarmentType.CROP_TOP: "t-shirt",
    GarmentType.SHIRT: "shirt",
    GarmentType.OVERSHIRT: "shirt",
    GarmentType.TUNIC: "blouse",
    GarmentType.BLOUSE: "blouse",
    GarmentType.KURTA: "shirt",
    GarmentType.SWEATSHIRT: "sweater",
    GarmentType.SWEATER: "sweater",
    GarmentType.CARDIGAN: "sweater",
    GarmentType.HOODIE: "hoodie",
    GarmentType.BLAZER: "blazer",
    GarmentType.WAISTCOAT: "blazer",
    GarmentType.NEHRU_JACKET: "blazer",
    GarmentType.JACKET: "jacket",
    GarmentType.DENIM_JACKET: "jacket",
    GarmentType.LEATHER_JACKET: "jacket",
    GarmentType.BOMBER: "jacket",
    GarmentType.PUFFER: "jacket",
    GarmentType.COAT: "coat",
    GarmentType.TRENCH_COAT: "coat",
    GarmentType.SHERWANI: "suit",
    GarmentType.SUIT: "suit",
    GarmentType.TROUSERS: "trousers",
    GarmentType.PALAZZO: "trousers",
    GarmentType.DHOTI: "trousers",
    GarmentType.LEGGINGS: "trousers",
    GarmentType.JOGGERS: "trousers",
    GarmentType.TRACK_PANTS: "trousers",
    GarmentType.JEANS: "jeans",
    GarmentType.CHINOS: "chinos",
    GarmentType.CARGO_PANTS: "chinos",
    GarmentType.SHORTS: "shorts",
    GarmentType.SKIRT: "skirt",
    GarmentType.DRESS: "dress",
    GarmentType.GOWN: "dress",
    GarmentType.ANARKALI: "dress",
    GarmentType.SALWAR_KAMEEZ: "dress",
    GarmentType.SAREE: "dress",
    GarmentType.LEHENGA: "dress",
    GarmentType.JUMPSUIT: "dress",
    GarmentType.ROMPER: "dress",
    GarmentType.CO_ORD_SET: "other",
    GarmentType.SNEAKERS: "shoes",
    GarmentType.SPORTS_SHOES: "shoes",
    GarmentType.FORMAL_SHOES: "shoes",
    GarmentType.LOAFERS: "shoes",
    GarmentType.BOOTS: "shoes",
    GarmentType.SANDALS: "shoes",
    GarmentType.HEELS: "shoes",
    GarmentType.FLATS: "shoes",
    GarmentType.FLIP_FLOPS: "shoes",
    GarmentType.JUTTIS: "shoes",
    GarmentType.OTHER: "other",
}
"""Fine type → live ``ClothingType`` value.

Scoring the current pipeline against fine labels directly would punish it for
distinctions it was never offered — it has no ``bomber`` to answer. Coarse
scoring asks only what it could have got right; the fine number is what Phase 2
must beat.
"""

COARSE_COLOR: dict[ColorName, str] = {
    ColorName.BLACK: "black",
    ColorName.CHARCOAL: "grey",
    ColorName.GREY: "grey",
    ColorName.LIGHT_GREY: "grey",
    ColorName.WHITE: "white",
    ColorName.OFF_WHITE: "white",
    ColorName.CREAM: "cream",
    ColorName.BEIGE: "beige",
    ColorName.TAN: "beige",
    ColorName.KHAKI: "beige",
    ColorName.CAMEL: "brown",
    ColorName.BROWN: "brown",
    ColorName.RUST: "orange",
    ColorName.MAROON: "maroon",
    ColorName.BURGUNDY: "maroon",
    ColorName.RED: "red",
    ColorName.CORAL: "pink",
    ColorName.PINK: "pink",
    ColorName.ORANGE: "orange",
    ColorName.MUSTARD: "yellow",
    ColorName.YELLOW: "yellow",
    ColorName.OLIVE: "olive",
    ColorName.GREEN: "green",
    ColorName.MINT: "green",
    ColorName.TEAL: "teal",
    ColorName.DENIM_BLUE: "blue",
    ColorName.BLUE: "blue",
    ColorName.NAVY: "navy",
    ColorName.LAVENDER: "purple",
    ColorName.PURPLE: "purple",
    ColorName.MULTICOLOR: "other",
    ColorName.OTHER: "other",
}
"""Fine colour → live ``Color`` value, same fairness argument as ``COARSE_TYPE``."""

COARSE_PATTERN: dict[PatternName, str] = {
    PatternName.SOLID: "solid",
    PatternName.STRIPED: "striped",
    PatternName.CHECKERED: "checkered",
    PatternName.PLAID: "plaid",
    PatternName.FLORAL: "floral",
    PatternName.POLKA_DOT: "polka_dot",
    PatternName.GEOMETRIC: "abstract",
    PatternName.ANIMAL_PRINT: "abstract",
    PatternName.CAMOUFLAGE: "abstract",
    PatternName.TIE_DYE: "abstract",
    PatternName.COLOR_BLOCK: "abstract",
    PatternName.EMBROIDERED: "other",
    PatternName.GRAPHIC_PRINT: "abstract",
    PatternName.ABSTRACT: "abstract",
    PatternName.OTHER: "other",
}
