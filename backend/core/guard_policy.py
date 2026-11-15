"""Upload-guard thresholds — where measurements and probabilities become decisions.

Same discipline as ``occasion_policy``: numbers live in code, versioned and
reviewable, never inside a prompt. Each value records where it came from. The
cost asymmetry decides the direction of every judgment call: rejecting a real
garment insults a user and loses the demo, while letting a car through
produces a silly outfit. So when in doubt the guard ``degrade``s, it does not
``reject``.
"""

from __future__ import annotations

CALIBRATED_FOR = "jev-1.13.0"

# ── Usability (code) ─────────────────────────────────────────────────

MIN_SIDE_PX = 120
"""Below this, there are not enough pixels to read a garment. Phone photos are
>1000 px; this only catches thumbnails and pasted icons."""

MIN_MEAN_LIGHTNESS = 4.0
"""Mean CIE L* below which nothing is lit. Measured on public: real photos
bottom out at 5.1 (p1 13.0); copies darkened to 6% brightness top out at 3.3.
The gap is narrow, so a real dim-room photo at L* ~5 will pass — the pixel
colour arm then reads it as near-black, which is the right failure to have."""

MIN_LIGHTNESS_SPREAD = 1.0
"""Std-dev of L* below which the frame is blank. One real photo sat at 2.8
(the first guess of 3.0 retook it); a solid synthetic frame measures ~0."""

MIN_SHARPNESS = 0.025
"""Re-blur residual over contrast. Public: the softest real photo is 0.029 (p1
0.034); blurred copies median 0.011, p95 0.023. Set a margin below the real
minimum rather than at the best-separating value, which would be fitted to the
very set it is reported on. An "overexposed" rule was dropped: a white-on-white
product shot legitimately averages L* 99, and blank frames are caught above."""

# ── "Is this clothing?" ──────────────────────────────────────────────

JEV_REJECT_BELOW = 0.5
JEV_UNSURE_BELOW = 0.7
"""On Jev's ``garment_photo`` noul, which judges the VLM's account of the photo.

0.5 is the noul's own midpoint, fixed before results. Measured: 0 of 139
garments below it (the lowest garment scored 0.74), 85% of non-garments caught
(87% excluding contested labels). The 0.7 degrade bar was placed below that
lowest garment, so it is fitted to this split; it only adds a caveat, never a
refusal."""
