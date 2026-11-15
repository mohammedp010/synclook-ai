"""Tests for the VLM garment describer — parsing leniency, request shape, caching.

The VLM is the one component in the cascade whose output format is a request,
not a contract, so the parser is the thing to pin: every way a small model
gets the format slightly wrong should still yield a usable description.
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from backend.core.config import Settings
from backend.services.garment_description import (
    GarmentDescriber,
    VLMUnavailableError,
    _jpeg_bytes,
    parse_description,
)

GOOD = """{
  "is_clothing_photo": true,
  "main_garment": {"item": "denim jacket", "colours": ["light blue", "white"], "pattern": "solid",
                   "fabric": "denim", "fit": "relaxed", "details": "point collar, chest pockets, metal buttons"},
  "other_garments": ["black jeans"],
  "setting": "on a hanger"
}"""


def _png(size: tuple[int, int] = (1200, 900)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, (30, 60, 120)).save(out, format="PNG")
    return out.getvalue()


# ── Parsing ──────────────────────────────────────────────────────────


def test_parses_the_requested_shape() -> None:
    d = parse_description(GOOD)
    assert d.parsed and d.is_clothing_photo
    assert d.item == "denim jacket"
    assert d.colours == ["light blue", "white"]
    assert d.other_garments == ["black jeans"]
    assert d.summary.startswith("light blue, white denim denim jacket")
    assert "solid" not in d.summary  # solid adds nothing


def test_json_inside_a_code_fence_or_prose_still_parses() -> None:
    d = parse_description(f"Sure! Here it is:\n```json\n{GOOD}\n```\nHope that helps.")
    assert d.parsed and d.item == "denim jacket"


def test_no_json_keeps_the_text_as_summary() -> None:
    d = parse_description("A light blue denim jacket hanging on a wall.")
    assert not d.parsed
    assert d.item is None
    assert "denim jacket" in d.summary


def test_null_like_strings_are_dropped_and_scalars_tolerated() -> None:
    d = parse_description(
        '{"main_garment": {"item": "loafers", "colours": "brown", "fit": "null", "fabric": "N/A"},'
        ' "other_garments": "x"}'
    )
    assert d.item == "loafers"
    assert d.colours == ["brown"]
    assert d.fit is None and d.fabric is None
    assert d.other_garments == []


def test_non_clothing_photo() -> None:
    d = parse_description('{"is_clothing_photo": false, "main_garment": null}')
    assert not d.is_clothing_photo
    assert d.item is None


# ── Image preparation ────────────────────────────────────────────────


def test_upload_is_downscaled_jpeg() -> None:
    jpeg = _jpeg_bytes(_png((2000, 1000)))
    img = Image.open(BytesIO(jpeg))
    assert img.format == "JPEG"
    assert max(img.size) == 512


# ── Client ───────────────────────────────────────────────────────────


class _FakeCompletions:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
            usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 900, "completion_tokens": 120, "cost": 0.0001}),
        )


def _describer(reply: str = GOOD, **overrides: Any) -> tuple[GarmentDescriber, _FakeCompletions]:
    completions = _FakeCompletions(reply)
    client: Any = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    settings = Settings(**({"vlm_api_key": "k", "vlm_model": "test/vlm"} | overrides))
    return GarmentDescriber(settings=settings, client=client), completions


async def test_request_shape_and_result() -> None:
    describer, completions = _describer()
    d = await describer.describe(_png())
    call = completions.calls[0]
    assert call["model"] == "test/vlm"
    assert call["temperature"] == 0.0
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "text" and "Do not say what occasion" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert d.item == "denim jacket"
    assert d.cost_usd == pytest.approx(0.0001)
    assert d.model == "test/vlm"


async def test_same_image_is_described_once() -> None:
    describer, completions = _describer()
    image = _png()
    first = await describer.describe(image)
    second = await describer.describe(image)
    assert second == replace(first, cost_usd=0.0, latency_ms=0.0)  # the cache hit was not billed
    assert len(completions.calls) == 1


async def test_unconfigured_describer_raises() -> None:
    describer = GarmentDescriber(settings=Settings(vlm_api_key="", vlm_model=""))
    assert not describer.enabled
    with pytest.raises(VLMUnavailableError):
        await describer.describe(_png())
