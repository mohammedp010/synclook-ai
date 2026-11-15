"""Tests for pixel colour extraction and its fusion with CLIP.

Synthetic images, not photos: each test pins one behaviour of the extractor —
the backdrop mask, the full-bleed fallback, the photographed-neutral bands, the
fusion arithmetic — so a regression names its cause. Whether the whole thing
is *accurate* is the perception eval's question, not these tests'.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from backend.schemas.taxonomy import ColorName
from backend.services.color_extraction import (
    ColorCluster,
    ColorReading,
    extract_colors,
    name_from_description,
    name_photographed,
    rgb_to_lab_array,
)
from backend.services.color_palette import colour_from_words, hex_to_rgb, name_hex, rgb_to_lab

NAVY = "#1b2a4a"
RED = "#c62330"


def _garment_on_backdrop(garment: str, backdrop: str = "#f4f4f4", size: int = 200) -> Image.Image:
    """A garment-coloured rectangle in the middle of a plain backdrop — a product shot."""
    img = Image.new("RGB", (size, size), hex_to_rgb_int(backdrop))
    ImageDraw.Draw(img).rectangle((size // 4, size // 5, 3 * size // 4, 4 * size // 5), fill=hex_to_rgb_int(garment))
    return img


def hex_to_rgb_int(value: str) -> tuple[int, int, int]:
    r, g, b = hex_to_rgb(value)
    return int(r), int(g), int(b)


def _reading(*clusters: tuple[ColorName, str, float]) -> ColorReading:
    built = [ColorCluster(name=n, hex=h, share=s, delta_e=0.0) for n, h, s in clusters]
    return ColorReading(
        primary=built[0].name,
        primary_hex=built[0].hex,
        secondary=None,
        secondary_hex=None,
        confidence=built[0].share,
        clusters=built,
        mask="border",
    )


# ── Vectorised LAB ───────────────────────────────────────────────────


def test_vectorised_lab_matches_scalar_conversion() -> None:
    samples = [(0.0, 0.0, 0.0), (255.0, 255.0, 255.0), (27.0, 42.0, 74.0), (198.0, 35.0, 48.0), (10.0, 200.0, 90.0)]
    batch = rgb_to_lab_array(np.array(samples))
    for row, rgb in zip(batch, samples):
        assert tuple(row) == pytest.approx(rgb_to_lab(rgb), abs=1e-6)


# ── Extraction ───────────────────────────────────────────────────────


def test_backdrop_is_masked_out_of_a_product_shot() -> None:
    reading = extract_colors(_garment_on_backdrop(NAVY))
    assert reading.mask == "border"
    assert reading.primary == ColorName.NAVY
    assert ColorName.WHITE not in {c.name for c in reading.clusters}


def test_full_bleed_close_up_abandons_the_mask() -> None:
    # The border *is* the garment. Masking it would leave nothing but noise,
    # which is the bug the centre check exists to stop.
    img = Image.new("RGB", (200, 200), hex_to_rgb_int(RED))
    reading = extract_colors(img)
    assert reading.mask == "centre"
    assert reading.primary == ColorName.RED
    assert reading.confidence == pytest.approx(1.0)


def test_two_colour_garment_reports_a_secondary() -> None:
    img = _garment_on_backdrop(NAVY)
    # Red lower half of the garment — a colour-blocked piece, not a logo.
    ImageDraw.Draw(img).rectangle((50, 100, 150, 160), fill=hex_to_rgb_int(RED))
    reading = extract_colors(img)
    assert {reading.primary, reading.secondary} == {ColorName.NAVY, ColorName.RED}
    assert reading.secondary_hex is not None


def test_small_trim_is_not_a_secondary_colour() -> None:
    img = _garment_on_backdrop(NAVY)
    ImageDraw.Draw(img).rectangle((95, 95, 105, 105), fill=hex_to_rgb_int(RED))  # a logo-sized patch
    reading = extract_colors(img)
    assert reading.primary == ColorName.NAVY
    assert reading.secondary is None


def test_extraction_is_deterministic() -> None:
    rng = np.random.default_rng(7)
    noisy = Image.fromarray(rng.integers(0, 255, (120, 90, 3), dtype=np.uint8))
    assert extract_colors(noisy) == extract_colors(noisy)


def test_hex_is_the_measured_colour_not_the_palette_anchor() -> None:
    reading = extract_colors(_garment_on_backdrop("#20304f"))
    assert reading.primary == ColorName.NAVY
    assert reading.primary_hex == "#20304f"


# ── Photographed neutrals ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hex_value", "expected"),
    [
        ("#1a1a1a", ColorName.BLACK),
        ("#3d3d3d", ColorName.CHARCOAL),
        ("#7a7a7a", ColorName.GREY),
        ("#b0b0b0", ColorName.LIGHT_GREY),
        # A white shirt as a phone photographs it (L* ≈ 82) — light grey by
        # ΔE against an ideal #fdfdfd anchor, white by band.
        ("#cdcdcd", ColorName.WHITE),
        ("#d6d0c2", ColorName.OFF_WHITE),
    ],
)
def test_neutrals_resolve_by_photographed_lightness(hex_value: str, expected: ColorName) -> None:
    assert name_photographed(hex_to_rgb(hex_value)) == expected


def test_dark_low_chroma_is_named_by_lightness_not_hue() -> None:
    # L* ≈ 15, C* ≈ 6 — where navy, black and brown all photograph. The pixels
    # cannot tell them apart, so the name is a lightness band and fusion decides.
    assert name_photographed(hex_to_rgb("#26252d")) == ColorName.BLACK


def test_saturated_colours_still_resolve_by_hue() -> None:
    assert name_photographed(hex_to_rgb(RED)) == ColorName.RED
    assert name_photographed(hex_to_rgb(NAVY)) == ColorName.NAVY


# ── Described colour (cascade) ───────────────────────────────────────

# The live upload that motivated it: light-wash denim (two blue-ish clusters,
# one named lavender) and 10% dark hair. Fusion shipped it as charcoal.
_DENIM_SHIRT = _reading(
    (ColorName.LAVENDER, "#a8bfd6", 0.43),
    (ColorName.DENIM_BLUE, "#7b93ad", 0.40),
    (ColorName.CHARCOAL, "#3b4046", 0.10),
    (ColorName.BROWN, "#735544", 0.07),
)


def test_described_family_takes_the_shade_from_the_pixels() -> None:
    named = name_from_description(_DENIM_SHIRT, ColorName.BLUE)
    assert (named.name, named.coarse, named.hex) == (ColorName.DENIM_BLUE, "blue", "#7b93ad")
    assert named.confidence == 0.40


def test_described_colour_with_no_cluster_keeps_the_word() -> None:
    named = name_from_description(_DENIM_SHIRT, ColorName.RED)
    assert (named.name, named.hex, named.confidence) == (ColorName.RED, name_hex(ColorName.RED), 0.0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("light blue", ColorName.BLUE),
        ("dark grey", ColorName.GREY),
        ("navy blue", ColorName.NAVY),
        ("Cream", ColorName.CREAM),
        ("silver", None),
        ("multicoloured", None),
        ("shimmering", None),
    ],
)
def test_colour_words(text: str, expected: ColorName | None) -> None:
    assert colour_from_words(text) == expected
