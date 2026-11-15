"""Tests for CIELAB colour resolution — the Phase 1 replacement for CLIP colour.

The ΔE2000 cases are the published reference pairs from Sharma, Wu & Dalal
(2005), the paper's own test data for implementations of the formula. They are
here because CIEDE2000 has several branches most inputs never reach — the hue
wrap-around, the ``C1'·C2' == 0`` guards, and the ``RT`` rotation term that only
matters in the blues — and an implementation can look right on ordinary colours
while being wrong in exactly the region where navy lives.
"""

from __future__ import annotations

import pytest

from backend.schemas.taxonomy import ColorName
from backend.services.color_palette import (
    PALETTE_HEX,
    chroma,
    delta_e2000,
    hex_to_rgb,
    nearest,
    resolve,
    rgb_to_hex,
    rgb_to_lab,
)

# (lab1, lab2, expected ΔE00) — Sharma et al. reference data.
CIEDE2000_CASES = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, -1.1848, -84.8006), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 2.5, 0.0), (50.0, 0.0, -2.5), 4.3065),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((50.0, 2.5, 0.0), (61.0, -5.0, 29.0), 22.8977),
    ((50.0, 2.5, 0.0), (56.0, -27.0, -3.0), 31.9030),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), CIEDE2000_CASES)
def test_delta_e2000_matches_reference_data(lab1, lab2, expected) -> None:
    assert delta_e2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_delta_e2000_is_zero_for_identical_colours() -> None:
    lab = rgb_to_lab((27.0, 42.0, 74.0))
    assert delta_e2000(lab, lab) == pytest.approx(0.0, abs=1e-9)


def test_delta_e2000_is_symmetric() -> None:
    a, b = rgb_to_lab((27.0, 42.0, 74.0)), rgb_to_lab((139.0, 141.0, 144.0))
    assert delta_e2000(a, b) == pytest.approx(delta_e2000(b, a), abs=1e-9)


# ── sRGB → LAB ───────────────────────────────────────────────────────


def test_lab_reference_points() -> None:
    """Pure white is L=100 on the neutral axis; pure black is L=0."""
    l_white, a_white, b_white = rgb_to_lab((255.0, 255.0, 255.0))
    assert l_white == pytest.approx(100.0, abs=1e-3)
    assert (a_white, b_white) == pytest.approx((0.0, 0.0), abs=1e-3)

    assert rgb_to_lab((0.0, 0.0, 0.0))[0] == pytest.approx(0.0, abs=1e-9)


def test_hex_round_trip() -> None:
    assert rgb_to_hex(hex_to_rgb("#1b2a4a")) == "#1b2a4a"
    assert hex_to_rgb("#abc") == hex_to_rgb("#aabbcc")


def test_hex_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        hex_to_rgb("not-a-colour")


def test_chroma_is_zero_on_the_neutral_axis() -> None:
    assert chroma(rgb_to_lab((128.0, 128.0, 128.0))) == pytest.approx(0.0, abs=0.05)


# ── Named resolution ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hex_value", "expected"),
    [
        ("#1b2a4a", ColorName.NAVY),
        ("#0d0d0d", ColorName.BLACK),
        ("#3a3d40", ColorName.CHARCOAL),
        ("#f8f8f8", ColorName.WHITE),
        ("#4a6d94", ColorName.DENIM_BLUE),
        ("#7a1f2b", ColorName.MAROON),
        ("#c9a227", ColorName.MUSTARD),
        ("#2f7d4f", ColorName.GREEN),
    ],
)
def test_resolve_picks_the_obvious_name(hex_value: str, expected: ColorName) -> None:
    assert nearest(hex_to_rgb(hex_value)) is expected


def test_navy_does_not_collapse_into_black_or_blue() -> None:
    """The failure the CLIP colour head makes constantly.

    Navy is the single most common menswear colour in the catalog, and it is
    the one CLIP most often reads as ``blue`` or ``black``.
    """
    assert nearest(hex_to_rgb("#1b2a4a")) is ColorName.NAVY
    assert nearest(hex_to_rgb("#16233d")) is ColorName.NAVY


def test_desaturated_colours_stay_neutral() -> None:
    """The chroma gate: a near-grey may not win a saturated name."""
    assert nearest(hex_to_rgb("#4a4d52")) in {
        ColorName.CHARCOAL,
        ColorName.GREY,
        ColorName.BLACK,
    }


def test_saturated_colours_never_return_a_neutral() -> None:
    for hex_value in ("#c62330", "#2361c4", "#e8761d", "#6b3fa0"):
        assert nearest(hex_to_rgb(hex_value)) not in {
            ColorName.GREY,
            ColorName.CHARCOAL,
            ColorName.BLACK,
            ColorName.WHITE,
        }


def test_resolve_returns_ranked_alternatives() -> None:
    ranked = resolve(hex_to_rgb("#1b2a4a"), top_k=3)
    assert len(ranked) == 3
    assert [d for _, d in ranked] == sorted(d for _, d in ranked)
    assert ranked[0][1] < ranked[-1][1]


def test_every_palette_anchor_resolves_to_itself() -> None:
    """Each reference point must be its own nearest name.

    A palette where one anchor is closer to a neighbour than to itself means
    two names have been placed too near each other to ever be distinguished.
    """
    for name, hex_value in PALETTE_HEX.items():
        assert nearest(hex_to_rgb(hex_value)) is name, f"{name.value} resolves to something else"
