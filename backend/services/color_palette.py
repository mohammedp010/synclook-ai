"""Named-colour resolution in CIELAB — the deterministic half of Phase 1.

Today's pipeline picks a colour by softmaxing seventeen CLIP prompts that
differ by one adjective (``"navy colored clothing"`` against ``"blue colored
clothing"``). Those prompts sit almost on top of each other in CLIP's text
space, so the winner turns on lighting rather than on the garment.

A garment's colour is a **measurable property of its pixels**, and the Jev
reference makes the general case for keeping it that way: *do not ask a model
for what code can compute exactly*, and *numeric colour representations
underperform semantic ones* — so the model's job is colour **semantics** ("does
this read as office-appropriate"), never colour **identity**.

This module owns identity. RGB → CIELAB → ΔE2000 against a reference palette,
which is perceptually uniform in a way RGB distance is not: RGB says navy and
black are far apart and that two mid-greens are far apart by the same amount,
and only one of those matches what an eye reports.

One non-obvious rule, ``_CHROMA_NEUTRAL_MAX``: below a chroma floor, only
neutrals may win. Without it a desaturated navy lands on charcoal, because at
low chroma ΔE is dominated by lightness and the hue that distinguishes them
carries almost no weight. Gating the candidate set on chroma is cheaper and
more reliable than trying to reweight the distance.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from backend.schemas.taxonomy import ColorName

# ──────────────────────────────────────────────────────────────────────
#  Reference palette
# ──────────────────────────────────────────────────────────────────────

PALETTE_HEX: dict[ColorName, str] = {
    ColorName.BLACK: "#111111",
    ColorName.CHARCOAL: "#36393d",
    ColorName.GREY: "#8b8d90",
    ColorName.LIGHT_GREY: "#c7c9cc",
    ColorName.WHITE: "#fdfdfd",
    ColorName.OFF_WHITE: "#f2efe7",
    ColorName.CREAM: "#f5e9cf",
    ColorName.BEIGE: "#dcc9a8",
    ColorName.TAN: "#c08f5e",
    ColorName.KHAKI: "#b3a369",
    ColorName.BROWN: "#6b4423",
    ColorName.CAMEL: "#b0764a",
    ColorName.RUST: "#a8422a",
    ColorName.MAROON: "#6d1f2b",
    ColorName.BURGUNDY: "#4f1424",
    ColorName.RED: "#c62330",
    ColorName.CORAL: "#f4756a",
    ColorName.PINK: "#eda0bd",
    ColorName.ORANGE: "#e8761d",
    ColorName.MUSTARD: "#d4a017",
    ColorName.YELLOW: "#f2d024",
    ColorName.OLIVE: "#6b6b34",
    ColorName.GREEN: "#2f7d4f",
    ColorName.MINT: "#a8ddc0",
    ColorName.TEAL: "#1f7a7a",
    ColorName.DENIM_BLUE: "#4a6d94",
    ColorName.BLUE: "#2361c4",
    ColorName.NAVY: "#1b2a4a",
    ColorName.LAVENDER: "#b7a6db",
    ColorName.PURPLE: "#6b3fa0",
}
"""sRGB anchors for each named colour. ``MULTICOLOR`` and ``OTHER`` are absent
on purpose — they are decided by pixel-cluster spread, not by proximity to a
reference point (see ``resolve``)."""

_NEUTRALS: frozenset[ColorName] = frozenset(
    {
        ColorName.BLACK,
        ColorName.CHARCOAL,
        ColorName.GREY,
        ColorName.LIGHT_GREY,
        ColorName.WHITE,
        ColorName.OFF_WHITE,
        ColorName.CREAM,
        ColorName.BEIGE,
    }
)

_CHROMA_NEUTRAL_MAX = 12.0
"""Below this LAB chroma, only neutrals may be returned. See module docstring."""

_CHROMA_NEUTRAL_MIN = 22.0
"""Above this chroma, neutrals are excluded — a saturated colour is not a grey
that happens to sit near one in lightness. Between the two bounds every
candidate competes, which is the honest answer for muted tones."""


# ──────────────────────────────────────────────────────────────────────
#  Colour-space conversion
# ──────────────────────────────────────────────────────────────────────

RGB = tuple[float, float, float]
LAB = tuple[float, float, float]

# D65 reference white.
_XN, _YN, _ZN = 0.95047, 1.00000, 1.08883
_DELTA = 6.0 / 29.0


def hex_to_rgb(value: str) -> RGB:
    """``'#1b2a4a'`` → ``(27.0, 42.0, 74.0)``."""
    text = value.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return tuple(float(int(text[i : i + 2], 16)) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: RGB) -> str:
    """``(27, 42, 74)`` → ``'#1b2a4a'``, clamped to the byte range."""
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def rgb_to_lab(rgb: RGB) -> LAB:
    """sRGB (0-255) → CIELAB, D65, via linearisation and XYZ."""

    def linearize(channel: float) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in rgb)

    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / _XN
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / _YN
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / _ZN

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > _DELTA**3 else t / (3 * _DELTA**2) + 4.0 / 29.0

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def chroma(lab: LAB) -> float:
    """LAB chroma — distance from the neutral axis. 0 is a perfect grey."""
    return math.hypot(lab[1], lab[2])


def delta_e2000(lab1: LAB, lab2: LAB) -> float:
    """CIEDE2000 colour difference.

    The current standard, and worth the arithmetic over the 1976 Euclidean
    version: it corrects for the eye's uneven sensitivity across the space —
    notably that blues need a rotation term and that differences compress as
    chroma rises. Roughly, ΔE < 2 is invisible, < 10 reads as "the same
    colour name", > 20 is plainly a different colour.
    """
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0

    c_bar7 = c_bar**7
    g = 0.5 * (1.0 - math.sqrt(c_bar7 / (c_bar7 + 25.0**7))) if c_bar > 0 else 0.0

    a1p, a2p = (1.0 + g) * a1, (1.0 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(ap: float, bp: float) -> float:
        if ap == 0.0 and bp == 0.0:
            return 0.0
        return math.degrees(math.atan2(bp, ap)) % 360.0

    h1p, h2p = hue(a1p, b1), hue(a2p, b2)

    dlp = l2 - l1
    dcp = c2p - c1p

    if c1p * c2p == 0.0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180.0:
        dhp = h2p - h1p
    elif h2p - h1p > 180.0:
        dhp = h2p - h1p - 360.0
    else:
        dhp = h2p - h1p + 360.0
    # ΔH′ — the spec's capital, and a different quantity from Δh′ above. Kept
    # cased as published so the line can be checked against the paper.
    dHp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)  # noqa: N806

    lp_bar = (l1 + l2) / 2.0
    cp_bar = (c1p + c2p) / 2.0

    if c1p * c2p == 0.0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180.0:
        hp_bar = (h1p + h2p) / 2.0
    elif h1p + h2p < 360.0:
        hp_bar = (h1p + h2p + 360.0) / 2.0
    else:
        hp_bar = (h1p + h2p - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(hp_bar - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * hp_bar))
        + 0.32 * math.cos(math.radians(3.0 * hp_bar + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * hp_bar - 63.0))
    )

    d_theta = 30.0 * math.exp(-(((hp_bar - 275.0) / 25.0) ** 2))
    cp_bar7 = cp_bar**7
    rc = 2.0 * math.sqrt(cp_bar7 / (cp_bar7 + 25.0**7)) if cp_bar > 0 else 0.0

    sl = 1.0 + (0.015 * (lp_bar - 50.0) ** 2) / math.sqrt(20.0 + (lp_bar - 50.0) ** 2)
    sc = 1.0 + 0.045 * cp_bar
    sh = 1.0 + 0.015 * cp_bar * t
    rt = -math.sin(math.radians(2.0 * d_theta)) * rc

    term_l = dlp / sl
    term_c = dcp / sc
    term_h = dHp / sh
    return math.sqrt(term_l**2 + term_c**2 + term_h**2 + rt * term_c * term_h)


# ──────────────────────────────────────────────────────────────────────
#  Resolution
# ──────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _palette_lab() -> dict[ColorName, LAB]:
    """Palette anchors in LAB, computed once."""
    return {name: rgb_to_lab(hex_to_rgb(value)) for name, value in PALETTE_HEX.items()}


def resolve(rgb: RGB, *, top_k: int = 3) -> list[tuple[ColorName, float]]:
    """Rank named colours by ΔE2000 against one sRGB triple.

    Returns ``(name, delta_e)`` best-first. The chroma gate in the module
    docstring decides which names are eligible before any distance is taken.
    """
    lab = rgb_to_lab(rgb)
    c = chroma(lab)

    if c <= _CHROMA_NEUTRAL_MAX:
        candidates = _NEUTRALS
    elif c >= _CHROMA_NEUTRAL_MIN:
        candidates = frozenset(PALETTE_HEX) - _NEUTRALS
    else:
        candidates = frozenset(PALETTE_HEX)

    scored = [(name, delta_e2000(lab, ref)) for name, ref in _palette_lab().items() if name in candidates]
    scored.sort(key=lambda pair: pair[1])
    return scored[:top_k]


def nearest(rgb: RGB) -> ColorName:
    """The single best named colour for one sRGB triple."""
    ranked = resolve(rgb, top_k=1)
    return ranked[0][0] if ranked else ColorName.OTHER


def name_hex(name: ColorName) -> str:
    """The reference hex for a named colour — used for UI swatches."""
    return PALETTE_HEX.get(name, "#888888")


# ── Colour words ─────────────────────────────────────────────────────

COLOUR_WORDS: dict[str, str] = {
    **{c.value.replace("_", " "): c.value for c in ColorName if c not in (ColorName.OTHER, ColorName.MULTICOLOR)},
    "off-white": ColorName.OFF_WHITE.value,
    "ivory": ColorName.OFF_WHITE.value,
    "gray": ColorName.GREY.value,
    "light gray": ColorName.LIGHT_GREY.value,
    "navy blue": ColorName.NAVY.value,
    "dark blue": ColorName.NAVY.value,
    "light blue": ColorName.BLUE.value,
    "sky blue": ColorName.BLUE.value,
    "royal blue": ColorName.BLUE.value,
    "dark wash": ColorName.DENIM_BLUE.value,
    "light wash": ColorName.DENIM_BLUE.value,
    "indigo": ColorName.DENIM_BLUE.value,
    "nude": ColorName.BEIGE.value,
    "dark brown": ColorName.BROWN.value,
    "light brown": ColorName.TAN.value,
    "dark green": ColorName.GREEN.value,
    "light green": ColorName.MINT.value,
    "light pink": ColorName.PINK.value,
    "hot pink": ColorName.PINK.value,
    "magenta": ColorName.PINK.value,
    "violet": ColorName.PURPLE.value,
    "lilac": ColorName.LAVENDER.value,
    "wine": ColorName.BURGUNDY.value,
    "crimson": ColorName.RED.value,
    "scarlet": ColorName.RED.value,
    "emerald": ColorName.GREEN.value,
    "multicoloured": ColorName.MULTICOLOR.value,
    "multicolored": ColorName.MULTICOLOR.value,
    "multicolour": ColorName.MULTICOLOR.value,
    "gold": "gold",
    "golden": "gold",
    "silver": "silver",
}
"""A VLM's colour words → ``ColorName`` values, plus the two metals."""

COLOUR_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(w) for w in sorted(COLOUR_WORDS, key=len, reverse=True)) + r")(?![\w-])"
)


def colour_from_words(text: str) -> ColorName | None:
    """The first plain colour named in ``text`` ("light blue" → blue); None for metals, mixes or no colour."""
    match = COLOUR_RE.search(text.lower())
    if match is None:
        return None
    value = COLOUR_WORDS[match.group(1)]
    if value not in ColorName._value2member_map_ or value == ColorName.MULTICOLOR.value:
        return None
    return ColorName(value)
