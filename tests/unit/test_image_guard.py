"""Tests for the upload guard — usability checks, the decision table, and how a decline surfaces.

Usability is code, so it is tested on images built in code. The decision table
is tested against ``guard_policy``'s own constants, so retuning a threshold
cannot silently invert a test.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from backend.core import guard_policy as policy
from backend.services.image_guard import (
    GuardOutcome,
    QualityReport,
    UnusableImageError,
    decide,
    quality_report,
)


def _textured(size: tuple[int, int] = (400, 300), seed: int = 3) -> Image.Image:
    """A photo-like image: blocks of colour with sharp edges and mid-tone exposure."""
    rng = np.random.default_rng(seed)
    blocks = rng.integers(40, 220, (size[1] // 20 + 1, size[0] // 20 + 1, 3), dtype=np.uint8)
    arr = np.kron(blocks, np.ones((20, 20, 1), dtype=np.uint8))[: size[1], : size[0]]
    return Image.fromarray(arr)


def _ok_quality() -> QualityReport:
    return QualityReport(min_side=800, mean_lightness=50.0, lightness_spread=20.0, sharpness=0.1, problems=())


# ── Usability ────────────────────────────────────────────────────────


def test_a_sharp_well_lit_photo_has_no_problems() -> None:
    assert quality_report(_textured()).problems == ()


@pytest.mark.parametrize(
    ("make", "problem"),
    [
        (lambda img: img.filter(ImageFilter.GaussianBlur(6)), "blurred"),
        (lambda img: img.point(lambda v: int(v * 0.04)), "too_dark"),
        (lambda img: Image.new("RGB", img.size, (200, 200, 200)), "blank"),
        (lambda img: img.resize((60, 45)), "too_small"),
    ],
)
def test_each_bad_photo_is_named(make: Any, problem: str) -> None:
    assert problem in quality_report(make(_textured())).problems


def test_a_dark_garment_on_a_lit_backdrop_is_not_too_dark() -> None:
    # Black clothes are not underexposed photos.
    img = Image.new("RGB", (400, 300), (225, 225, 225))
    img.paste(Image.new("RGB", (200, 200), (12, 12, 14)), (100, 50))
    assert "too_dark" not in quality_report(img).problems


# ── Decision table ───────────────────────────────────────────────────


def test_usability_wins_over_everything() -> None:
    bad = QualityReport(min_side=800, mean_lightness=2.0, lightness_spread=5.0, sharpness=0.1, problems=("too_dark",))
    decision = decide(bad)
    assert decision.outcome == GuardOutcome.RETAKE
    assert decision.reason == "too_dark"
    assert "dark" in decision.message


def test_jev_decides_is_this_clothing() -> None:
    q = _ok_quality()
    rejected = decide(q, jev_garment_p=policy.JEV_REJECT_BELOW - 0.01, subject="a red car")
    assert rejected.outcome == GuardOutcome.REJECT
    assert "a red car" in rejected.message
    assert decide(q, jev_garment_p=policy.JEV_UNSURE_BELOW - 0.01).outcome == GuardOutcome.DEGRADE
    assert decide(q, jev_garment_p=0.99).outcome == GuardOutcome.PASS


def test_no_judgment_skips_the_clothing_check() -> None:
    assert decide(_ok_quality()).outcome == GuardOutcome.PASS


def test_multiple_garments_degrade_rather_than_reject() -> None:
    decision = decide(_ok_quality(), garment_count=3, main_item="denim jacket")
    assert decision.outcome == GuardOutcome.DEGRADE
    assert decision.reason == "multiple_garments"
    assert "denim jacket" in decision.message


def test_one_other_item_is_not_an_outfit() -> None:
    assert decide(_ok_quality(), garment_count=2).outcome == GuardOutcome.PASS


def test_parts_and_tags_are_not_separate_garments() -> None:
    from backend.services.image_guard import separate_items

    others = [
        "purple lining",
        "white price tag",
        "brown ribbed cuffs",
        "black trousers",
        "gold shoe tree",
        "white sneakers",
    ]
    assert separate_items(others) == ["black trousers", "white sneakers"]


# ── HTTP surface ─────────────────────────────────────────────────────


def test_decline_is_a_422_with_a_readable_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app import create_app

    app = create_app()

    @app.get("/_guard_probe")
    async def _probe() -> None:
        raise UnusableImageError(decide(_ok_quality(), jev_garment_p=0.0, subject="a red car"))

    response = TestClient(app).get("/_guard_probe")
    assert response.status_code == 422
    body = response.json()
    assert body["guard"] == "reject" and body["reason"] == "not_clothing"
    assert "a red car" in body["detail"]  # the frontend shows `detail` verbatim


def test_retake_message_is_specific() -> None:
    img = _textured().filter(ImageFilter.GaussianBlur(6))
    out = BytesIO()
    img.save(out, format="PNG")
    decision = decide(quality_report(img))
    assert decision.outcome == GuardOutcome.RETAKE
    assert "blurry" in decision.message
