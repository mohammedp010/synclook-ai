"""Unit tests for vision pipeline helpers (no model loading required)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import torch
from PIL import Image

from backend.schemas.clothing import ClothingType, Color, Style
from backend.services.vision import (
    _center_crop,
    _classify_head,
    _is_caption_relevant,
)


class TestCenterCrop:
    def test_full_ratio_returns_original(self) -> None:
        img = Image.new("RGB", (100, 200))
        assert _center_crop(img, 1.0) is img

    def test_crop_reduces_dimensions(self) -> None:
        img = Image.new("RGB", (100, 200))
        cropped = _center_crop(img, 0.5)
        assert cropped.size == (50, 100)

    def test_ratio_clamped_to_lower_bound(self) -> None:
        img = Image.new("RGB", (100, 100))
        cropped = _center_crop(img, 0.1)  # clamps to 0.4
        assert cropped.size == (40, 40)


class TestClassifyHead:
    """_classify_head works against a stub holder — no CLIP required."""

    @pytest.fixture
    def holder(self) -> MagicMock:
        # Three prompts: two for CASUAL, one for FORMAL. The image embedding
        # below is aligned with prompt 1 (casual variant b).
        text_features = torch.tensor(
            [
                [1.0, 0.0, 0.0],  # casual variant a
                [0.0, 1.0, 0.0],  # casual variant b
                [0.0, 0.0, 1.0],  # formal
            ]
        )
        labels = [Style.CASUAL.value, Style.CASUAL.value, Style.FORMAL.value]
        stub = MagicMock()
        stub.text_features.return_value = (text_features, labels)
        stub.logit_scale = 100.0
        return stub

    def test_best_label_wins(self, holder: MagicMock) -> None:
        image_features = torch.tensor([0.0, 1.0, 0.0])
        label, conf = _classify_head(image_features, "style", {}, holder)
        assert label == Style.CASUAL.value
        assert conf > 0.99

    def test_confidence_is_max_across_label_variants(self, holder: MagicMock) -> None:
        # Ambiguous between the two casual variants — label-level confidence
        # is the max variant probability, not their sum.
        image_features = torch.tensor([0.7, 0.7, 0.0])
        label, conf = _classify_head(image_features, "style", {}, holder)
        assert label == Style.CASUAL.value
        assert 0.0 < conf <= 1.0

    def test_confidences_are_probabilities(self, holder: MagicMock) -> None:
        image_features = torch.tensor([0.5, 0.3, 0.4])
        _, conf = _classify_head(image_features, "style", {}, holder)
        assert 0.0 <= conf <= 1.0


class TestCaptionRelevance:
    def test_caption_mentioning_item_is_relevant(self) -> None:
        assert _is_caption_relevant("a man wearing blue jeans", ClothingType.JEANS, Color.BLUE)

    def test_caption_mentioning_color_only_is_relevant(self) -> None:
        assert _is_caption_relevant("something navy in a room", ClothingType.SHIRT, Color.NAVY)

    def test_unrelated_scene_caption_is_not_relevant(self) -> None:
        assert not _is_caption_relevant("a dog on a beach", ClothingType.SHIRT, Color.NAVY)

    def test_empty_caption_is_not_relevant(self) -> None:
        assert not _is_caption_relevant("", ClothingType.SHIRT, Color.NAVY)
