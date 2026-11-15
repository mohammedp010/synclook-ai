"""Garment colour from pixels — the exact shade behind the vision model's colour word.

``color_palette`` answers "which named colour is this one RGB triple". This
module answers the questions on either side of it: *which pixels are the
garment and what colours are they* (``extract_colors``), and *which of those
colours would a person name* (``name_from_description``: the model's word
picks the family, the pixels the shade).

Extraction:

1. Downscale. Colour is a low-frequency property; 160px is plenty.
2. Mask the background by sampling the image border. Product shots, flat lays
   and hanger photos sit on a backdrop that touches the frame edge, and the
   garment mostly does not. Pixels close (ΔE76) to a border mode are backdrop.
   The mask is abandoned for a plain centre prior when it removes nearly
   everything, or when it calls the centre of the frame backdrop — a full-bleed
   close-up, where the border *is* the garment and masking it would leave only
   the shadows in its folds.
3. Weight what survives toward the frame centre.
4. Weighted k-means in CIELAB. Deterministic: fixed-seed k-means++ init and a
   strided (not random) subsample, so one photo always gives one answer.
5. Name each cluster as photographed (see ``name_photographed``) and merge
   clusters sharing a name — the lit and shadowed sides of a fold are one colour.

Why pixels alone are not the answer — measured on the ``public`` split, n=139,
coarse colour accuracy: CLIP 0.496, pixels alone 0.410, fused 0.561. The
pixel arm's errors were not noise; they were two systematic findings:

- **Colour names are categorical and object-conditioned.** A cognac penny loafer
  is "brown" to a person and rust to a spectrometer; an acid-wash jacket is
  "blue denim" while its pixels are pale grey-blue. The pixels were right and
  the name was wrong. CLIP, having seen the object, names it like a person.
- **Dark garments carry almost no hue.** Navy, black, brown, teal and maroon all
  photographed at L* 5-30, C* 4-10; the lighting cast is as large as the hue.
  No threshold separates them, and an attempt to defer only that zone to CLIP
  (0.432) was strictly worse than fusing everywhere.

So neither arm decides alone. CLIP proposes a distribution over colour names;
the pixels say which of those colours are physically present; the product of
the two picks the name, and the pixels supply the shade, hex and secondary.

Needs only numpy and Pillow. ``rembg``/U²-Net would
mask better on cluttered on-body photos at the cost of ~170MB of model and
onnxruntime; the eval decides whether that upgrade is worth paying for.

What this cannot do: pick *which* garment a multi-garment photo is about. On an
on-body shot of shirt and jeans the pixels report the dominant areas. That is
Phase 3's multi-garment branch, not a tuning problem here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from backend.schemas.taxonomy import COARSE_COLOR, ColorName
from backend.services.color_palette import (
    PALETTE_HEX,
    RGB,
    chroma,
    delta_e2000,
    hex_to_rgb,
    name_hex,
    resolve,
    rgb_to_hex,
    rgb_to_lab,
)

FloatArray = NDArray[np.float64]

_MAX_SIDE = 160
"""Downscale target for the long edge."""

_BORDER_FRACTION = 0.06
"""Width of the border ring sampled for background, as a fraction of each side."""

_BG_MODE_MIN_SHARE = 0.15
"""A border cluster must cover this much of the ring to count as backdrop —
smaller ones are usually the garment itself touching the frame edge."""

_BG_DISTANCE = 14.0
"""ΔE76 within which a pixel is taken to be backdrop."""

_MIN_FOREGROUND = 0.08
"""Below this surviving fraction the mask is presumed wrong and abandoned."""

_CENTRE_MASKED_MAX = 0.5
"""If more than this share of the central third is called backdrop, the
"backdrop" is the garment filling the frame and the mask is abandoned."""

_CENTRE_SIGMA = 0.35
"""Centre-prior Gaussian width, as a fraction of each image side."""

_K = 4
_KMEANS_ITERS = 15
_MAX_SAMPLES = 5000

_SECONDARY_MIN_SHARE = 0.18
"""A second colour has to cover this much of the garment to be worth naming.
Below it, it is trim, a logo or a shadow, and calling it a secondary colour
would make the stylist match against a detail."""

# ── Photographed neutrals ────────────────────────────────────────────
# The palette anchors are ideal dye colours. A camera does not see those: on
# the public split, white garments came back at L* 77-88 and black ones at
# L* 20-31, because nobody lights a phone photo like a colour booth. Matching
# neutrals by ΔE against ideal anchors turned every white shirt light grey and
# every black shoe charcoal. Neutrals are resolved by lightness band instead,
# with the bands set where photographed garments actually land.

_NEUTRAL_CHROMA = 9.0
"""Below this chroma a cluster is named as a neutral."""

_DARK_L = 35.0
_DARK_CHROMA = 12.0
"""Below ``_DARK_L``, chroma up to ``_DARK_CHROMA`` is lighting cast, not hue."""

_NEUTRAL_BANDS: tuple[tuple[float, ColorName], ...] = (
    (24.0, ColorName.BLACK),
    (42.0, ColorName.CHARCOAL),
    (62.0, ColorName.GREY),
    (75.0, ColorName.LIGHT_GREY),
)
"""Upper L* bound per neutral, ascending. Anything brighter is white."""

_BAND_NEUTRALS: frozenset[ColorName] = frozenset(
    {n for _, n in _NEUTRAL_BANDS} | {ColorName.WHITE, ColorName.OFF_WHITE}
)
"""Neutrals the band rule owns. Cream and beige are tinted, so they stay in the
ΔE ranking with the chromatic colours."""

_WARM_WHITE_B = 5.0
"""A bright neutral with b* above this reads off-white rather than white."""


@dataclass(frozen=True)
class ColorCluster:
    name: ColorName
    hex: str
    share: float
    delta_e: float
    """ΔE2000 to the named colour's anchor — how well the name fits."""


@dataclass(frozen=True)
class ColorReading:
    """What the pixels say, before any model is consulted."""

    primary: ColorName
    primary_hex: str
    secondary: ColorName | None
    secondary_hex: str | None
    confidence: float
    """Share of the (centre-weighted) garment covered by the primary cluster."""
    clusters: list[ColorCluster]
    mask: str
    """``"border"`` when the backdrop mask held, ``"centre"`` when it was abandoned."""


@dataclass(frozen=True)
class FusedColor:
    """The colour the pipeline reports: CLIP's naming, constrained by the pixels."""

    name: ColorName
    coarse: str
    """The live ``Color`` value — ``COARSE_COLOR[name]``."""
    hex: str
    secondary: ColorName | None
    secondary_hex: str | None
    confidence: float
    """Winner's share of the normalised CLIP × pixel product."""


# ──────────────────────────────────────────────────────────────────────
#  Vectorised colour space — the scalar versions live in color_palette
# ──────────────────────────────────────────────────────────────────────

_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_WHITE = np.array([0.95047, 1.00000, 1.08883])
_DELTA = 6.0 / 29.0


def rgb_to_lab_array(rgb: FloatArray) -> FloatArray:
    """``(N, 3)`` sRGB 0-255 → ``(N, 3)`` CIELAB, D65. Matches ``color_palette.rgb_to_lab``."""
    c = rgb / 255.0
    linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = (linear @ _XYZ.T) / _WHITE
    f = np.where(xyz > _DELTA**3, np.cbrt(xyz), xyz / (3 * _DELTA**2) + 4.0 / 29.0)
    return np.stack(
        [116.0 * f[:, 1] - 16.0, 500.0 * (f[:, 0] - f[:, 1]), 200.0 * (f[:, 1] - f[:, 2])],
        axis=1,
    )


# ──────────────────────────────────────────────────────────────────────
#  Weighted k-means
# ──────────────────────────────────────────────────────────────────────


def _kmeans(points: FloatArray, weights: FloatArray, k: int, seed: int = 0) -> tuple[FloatArray, NDArray[np.intp]]:
    """Weighted k-means with k-means++ init. Returns (centres, assignment)."""
    rng = np.random.default_rng(seed)
    k = min(k, len(points))
    centres = [points[rng.choice(len(points), p=weights / weights.sum())]]
    for _ in range(1, k):
        d2 = np.min(((points[:, None, :] - np.array(centres)[None, :, :]) ** 2).sum(-1), axis=1)
        mass = d2 * weights
        if mass.sum() <= 0:
            break
        centres.append(points[rng.choice(len(points), p=mass / mass.sum())])
    c = np.array(centres)

    assign = np.zeros(len(points), dtype=np.intp)
    weighted = points * weights[:, None]
    for _ in range(_KMEANS_ITERS):
        assign = np.argmin(((points[:, None, :] - c[None, :, :]) ** 2).sum(-1), axis=1)
        mass = np.bincount(assign, weights=weights, minlength=len(c))
        sums = np.stack([np.bincount(assign, weights=weighted[:, d], minlength=len(c)) for d in range(3)], axis=1)
        moved = np.where(mass[:, None] > 0, sums / np.maximum(mass, 1e-12)[:, None], c)
        converged = np.allclose(moved, c, atol=0.1)
        c = moved
        if converged:
            break
    return c, assign


# ──────────────────────────────────────────────────────────────────────
#  Extraction
# ──────────────────────────────────────────────────────────────────────


def _downscale(image: Image.Image) -> FloatArray:
    img = image.convert("RGB")
    scale = _MAX_SIDE / max(img.size)
    if scale < 1.0:
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(size, Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.float64)


def _background_mask(lab: FloatArray) -> NDArray[np.bool_]:
    """True where a pixel looks like the backdrop sampled from the frame border."""
    h, w, _ = lab.shape
    bh, bw = max(1, round(h * _BORDER_FRACTION)), max(1, round(w * _BORDER_FRACTION))
    ring = np.zeros((h, w), dtype=bool)
    ring[:bh, :] = ring[-bh:, :] = True
    ring[:, :bw] = ring[:, -bw:] = True

    border = lab[ring]
    centres, assign = _kmeans(border, np.ones(len(border)), k=3)
    shares = np.bincount(assign, minlength=len(centres)) / len(border)
    modes = centres[shares >= _BG_MODE_MIN_SHARE]
    if len(modes) == 0:
        return np.zeros((h, w), dtype=bool)

    flat = lab.reshape(-1, 3)
    dist = np.sqrt(((flat[:, None, :] - modes[None, :, :]) ** 2).sum(-1)).min(axis=1)
    return np.asarray((dist < _BG_DISTANCE).reshape(h, w))


def _centre_weights(h: int, w: int) -> FloatArray:
    ys = (np.arange(h) - (h - 1) / 2) / (h * _CENTRE_SIGMA)
    xs = (np.arange(w) - (w - 1) / 2) / (w * _CENTRE_SIGMA)
    return np.asarray(np.exp(-0.5 * (ys[:, None] ** 2 + xs[None, :] ** 2)))


def name_photographed(rgb: RGB) -> ColorName:
    """Name one cluster colour as a camera would have recorded it.

    Neutrals — and dark colours whose chroma is within lighting-cast range — go
    by lightness band (``_NEUTRAL_BANDS``). Anything with real chroma goes to
    ``color_palette.resolve``'s ΔE2000 ranking, minus the band-owned neutrals.
    """
    lab = rgb_to_lab(rgb)
    c = chroma(lab)
    if c < _NEUTRAL_CHROMA or (lab[0] < _DARK_L and c < _DARK_CHROMA):
        band = next((name for bound, name in _NEUTRAL_BANDS if lab[0] < bound), None)
        if band is not None:
            return band
        return ColorName.OFF_WHITE if lab[2] > _WARM_WHITE_B else ColorName.WHITE

    ranked = resolve(rgb, top_k=len(PALETTE_HEX))
    return next((name for name, _ in ranked if name not in _BAND_NEUTRALS), ranked[0][0])


def extract_colors(image: Image.Image) -> ColorReading:
    """Dominant garment colours of one image, from pixels alone. Deterministic."""
    rgb = _downscale(image)
    h, w, _ = rgb.shape
    lab = rgb_to_lab_array(rgb.reshape(-1, 3)).reshape(h, w, 3)

    background = _background_mask(lab)
    keep = ~background
    mask = "border"
    ch, cw = h // 3, w // 3
    if keep.mean() < _MIN_FOREGROUND or background[ch : h - ch, cw : w - cw].mean() > _CENTRE_MASKED_MAX:
        keep = np.ones((h, w), dtype=bool)
        mask = "centre"

    weights = _centre_weights(h, w)[keep]
    points_lab = lab[keep]
    points_rgb = rgb[keep]
    if len(points_lab) > _MAX_SAMPLES:
        idx = np.linspace(0, len(points_lab) - 1, _MAX_SAMPLES).astype(np.intp)
        points_lab, points_rgb, weights = points_lab[idx], points_rgb[idx], weights[idx]

    _, assign = _kmeans(points_lab, weights, k=_K)

    merged: dict[ColorName, tuple[float, FloatArray]] = {}
    total = float(weights.sum())
    for j in np.unique(assign):
        member = assign == j
        w_j = float(weights[member].sum())
        mean_rgb = (points_rgb[member] * weights[member][:, None]).sum(0) / w_j
        name = name_photographed((float(mean_rgb[0]), float(mean_rgb[1]), float(mean_rgb[2])))
        prev_w, prev_rgb = merged.get(name, (0.0, np.zeros(3)))
        new_w = prev_w + w_j
        merged[name] = (new_w, (prev_rgb * prev_w + mean_rgb * w_j) / new_w)

    clusters: list[ColorCluster] = []
    for name, (weight, mean_rgb) in merged.items():
        triple = (float(mean_rgb[0]), float(mean_rgb[1]), float(mean_rgb[2]))
        delta_e = delta_e2000(rgb_to_lab(triple), rgb_to_lab(hex_to_rgb(name_hex(name))))
        clusters.append(
            ColorCluster(name=name, hex=rgb_to_hex(triple), share=round(weight / total, 4), delta_e=round(delta_e, 2))
        )
    clusters.sort(key=lambda cl: cl.share, reverse=True)

    primary = clusters[0]
    secondary = next((cl for cl in clusters[1:] if cl.share >= _SECONDARY_MIN_SHARE), None)
    return ColorReading(
        primary=primary.name,
        primary_hex=primary.hex,
        secondary=secondary.name if secondary else None,
        secondary_hex=secondary.hex if secondary else None,
        confidence=round(primary.share, 3),
        clusters=clusters,
        mask=mask,
    )


# ──────────────────────────────────────────────────────────────────────
#  Naming
# ──────────────────────────────────────────────────────────────────────


def name_from_description(reading: ColorReading, described: ColorName) -> FusedColor:
    """The VLM's colour word picks the family; the pixels pick the shade and hex inside it.

    Colour names are object-conditioned: washed denim photographs as a
    low-chroma blue that sits nearer the grey anchors than the blue ones, so
    pixels outvoted CLIP's "blue" and a light-blue denim shirt shipped as
    charcoal (live upload, 2026-10-07). A VLM that sees the garment names it
    the way a person would. On the public split (n=139, Gemini 2.5 Flash-Lite)
    coarse accuracy went 0.561 → 0.647 and fine 0.489 → 0.532 over the old
    CLIP x pixel fusion. Confidence is the share of the cluster that carries
    the shade, or 0 when no cluster is in the family.
    """
    fused = _in_family(reading, COARSE_COLOR[described], 0.0)
    cluster = next((cl for cl in reading.clusters if cl.name == fused.name and cl.hex == fused.hex), None)
    if cluster is None:
        # No pixel cluster in the named family: the word itself, on its own swatch.
        return replace(fused, name=described, coarse=COARSE_COLOR[described], hex=name_hex(described))
    return replace(fused, confidence=round(cluster.share, 3))


def _in_family(reading: ColorReading, family: str, confidence: float) -> FusedColor:
    cluster = next((cl for cl in reading.clusters if COARSE_COLOR[cl.name] == family), None)
    if cluster is not None:
        name, hex_value = cluster.name, cluster.hex
    else:
        # Every live Color value is also a ColorName, so the family names itself.
        name = ColorName(family)
        hex_value = name_hex(name)

    secondary = next(
        (
            cl
            for cl in reading.clusters
            if COARSE_COLOR[cl.name] != family and cl.share >= _SECONDARY_MIN_SHARE and cl is not cluster
        ),
        None,
    )
    return FusedColor(
        name=name,
        coarse=COARSE_COLOR[name],
        hex=hex_value,
        secondary=secondary.name if secondary else None,
        secondary_hex=secondary.hex if secondary else None,
        confidence=round(confidence, 3),
    )
