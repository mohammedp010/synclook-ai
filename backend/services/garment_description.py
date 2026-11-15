"""Garment description from a budget VLM — the "seeing in words" layer (plan L2).

Jev is text-only (reference §5.5), so something has to turn the photograph into
words before it can be judged. CLIP cannot: its text tower only *scores* a fixed
prompt list. This module asks a small multimodal model to **describe, not
decide** — what garments are visible, in what fabric, fit, colours and details —
and hands that to ``garment_judge``. The VLM is never asked for occasion,
formality or style: those are judgments, it would answer in prose, and the
pipeline would be back to parsing opinions.

The output is JSON because the *shape* of a description is fixed even though
its content is free text. Parsing is lenient: a model that wraps the JSON in a
code fence or prose still yields a description, and one that returns no JSON
at all still yields its raw text as ``summary``. A description that failed to
parse is worth more to Jev than no description.

Cost discipline:

- the image is downscaled to ``_MAX_SIDE`` px before upload — vision tokens
  scale with resolution, and garment identity does not need more;
- ``temperature=0`` and a ``vlm_max_tokens`` ceiling bound the output;
- results are cached by image hash (in-process LRU here; the perception eval
  adds an on-disk cache so a re-run costs nothing).

Failures raise ``VLMUnavailableError``; the caller decides what that means.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from io import BytesIO
from typing import Any

from openai import APIError, APITimeoutError, AsyncOpenAI
from PIL import Image

from backend.core.config import Settings, get_settings
from backend.core.exceptions import SynclookError
from backend.core.logging import get_logger

logger = get_logger(__name__)

_MAX_SIDE = 512
_JPEG_QUALITY = 85
_CACHE_SIZE = 256

PROMPT = """Describe the clothing in this photo for a stylist who cannot see it.

Describe only what is visible. Do not say what occasion, style or formality it suits.

Return only JSON, no prose, in exactly this shape:
{
  "subject": "what the photo mainly shows, in a few words, e.g. 'a brown loafer', 'a man in a suit', 'a red car'",
  "is_clothing_photo": true,
  "main_garment": {
    "item": "the most specific everyday name, e.g. 'denim jacket', 'penny loafers', 'anarkali kurta', 'leather belt'",
    "colours": ["main colour first, in plain words"],
    "pattern": "solid, striped, checked, floral, embroidered, printed graphic, ...",
    "fabric": "best guess, e.g. cotton, denim, wool, leather, silk, knit",
    "fit": "e.g. slim, relaxed, oversized, tailored, flowy; or null",
    "details": "collar, sleeves, length, closures, hardware, embellishment — one short sentence"
  },
  "other_garments": ["other visible clothing items or accessories, each as 'colour item'"],
  "setting": "product shot, worn by a person, flat lay, on a hanger, mirror selfie, or other"
}

The main garment is the one the photo is about — the most central or prominent item.
Set is_clothing_photo to true only if the photo is mainly about clothing, footwear or an
accessory — a garment shown on its own, or a person photographed to show what they wear.
If clothing is only incidental (a crowd, a stage, a vehicle, an animal, a logo, a
building), set it to false and main_garment to null."""

PROMPT_VERSION = hashlib.sha256(PROMPT.encode()).hexdigest()[:8]
"""Part of every cache key, so editing the prompt can never serve a reply to the old one."""


class VLMUnavailableError(SynclookError):
    """The VLM could not describe the image — not configured, timed out, or errored. Callers fail open."""


@dataclass(frozen=True)
class VisualDescription:
    is_clothing_photo: bool
    item: str | None
    colours: list[str] = field(default_factory=list)
    pattern: str | None = None
    fabric: str | None = None
    fit: str | None = None
    details: str | None = None
    other_garments: list[str] = field(default_factory=list)
    setting: str | None = None
    subject: str | None = None
    """What the photo mainly shows, whether or not it is clothing — the guardrail's input."""
    summary: str = ""
    """One line of prose, built from the fields — or the raw reply when it held no JSON."""
    model: str = ""
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    parsed: bool = True

    def detail_text(self) -> str:
        """The description as one sentence for Jev's ``state``."""
        return self.summary


def _jpeg_bytes(image_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((_MAX_SIDE, _MAX_SIDE), Image.Resampling.LANCZOS)
    out = BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_QUALITY)
    return out.getvalue()


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"null", "none", "n/a", "unknown"} else None


def _summarise(
    item: str | None, colours: list[str], pattern: str | None, fabric: str | None, fit: str | None, details: str | None
) -> str:
    head = " ".join(x for x in (", ".join(colours[:2]) or None, fabric, item) if x)
    parts = [head] if head else []
    if pattern and pattern.lower() != "solid":
        parts.append(f"{pattern} pattern")
    if fit:
        parts.append(f"{fit} fit")
    if details:
        parts.append(details.rstrip("."))
    return "; ".join(parts)


def parse_description(text: str) -> VisualDescription:
    """Lenient JSON → ``VisualDescription``. Never raises on content."""
    match = _JSON_BLOCK.search(text or "")
    data: dict[str, Any] | None = None
    if match:
        try:
            loaded = json.loads(match.group(0))
            data = loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            data = None
    if data is None:
        return VisualDescription(is_clothing_photo=True, item=None, summary=(text or "").strip()[:400], parsed=False)

    raw_main = data.get("main_garment")
    main: dict[str, Any] = raw_main if isinstance(raw_main, dict) else {}
    raw_colours = main.get("colours") or []
    colours = [c for c in (_clean(x) for x in (raw_colours if isinstance(raw_colours, list) else [raw_colours])) if c]
    item, pattern, fabric = _clean(main.get("item")), _clean(main.get("pattern")), _clean(main.get("fabric"))
    fit, details = _clean(main.get("fit")), _clean(main.get("details"))
    others_raw = data.get("other_garments") or []
    others = [o for o in (_clean(x) for x in (others_raw if isinstance(others_raw, list) else [])) if o]
    return VisualDescription(
        is_clothing_photo=bool(data.get("is_clothing_photo", True)),
        item=item,
        colours=colours,
        pattern=pattern,
        fabric=fabric,
        fit=fit,
        details=details,
        other_garments=others,
        setting=_clean(data.get("setting")),
        subject=_clean(data.get("subject")),
        summary=_summarise(item, colours, pattern, fabric, fit, details),
    )


class GarmentDescriber:
    """Async VLM client over any OpenAI-compatible endpoint (OpenRouter by default)."""

    def __init__(self, settings: Settings | None = None, client: AsyncOpenAI | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client
        if self._client is None and self.enabled:
            self._client = AsyncOpenAI(
                api_key=self._settings.vlm_api_key,
                base_url=self._settings.vlm_base_url,
                timeout=self._settings.vlm_timeout_seconds,
                max_retries=1,
            )
        self._cache: OrderedDict[str, VisualDescription] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return bool(self._settings.vlm_api_key and self._settings.vlm_model)

    @property
    def model(self) -> str:
        return self._settings.vlm_model

    async def describe(self, image_bytes: bytes) -> VisualDescription:
        if not self.enabled or self._client is None:
            raise VLMUnavailableError("VLM is not configured (VLM_API_KEY / VLM_MODEL unset)")

        key = f"{PROMPT_VERSION}:{hashlib.sha256(image_bytes).hexdigest()}"
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            # This call was not billed; the cost on the cached reply was the first call's.
            return replace(cached, cost_usd=0.0, latency_ms=0.0)

        data_url = "data:image/jpeg;base64," + base64.b64encode(_jpeg_bytes(image_bytes)).decode()
        started = time.perf_counter()
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                max_tokens=self._settings.vlm_max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                # OpenRouter: report the real charge for this call in `usage`.
                extra_body={"usage": {"include": True}},
            )
        except APITimeoutError as exc:
            raise VLMUnavailableError("VLM timed out") from exc
        except APIError as exc:
            raise VLMUnavailableError(f"VLM request failed: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0

        text = resp.choices[0].message.content or "" if resp.choices else ""
        usage = resp.usage.model_dump() if resp.usage else {}
        description = parse_description(text)
        description = VisualDescription(
            **{
                **description.__dict__,
                "model": resp.model or self.model,
                "latency_ms": round(latency_ms, 1),
                "cost_usd": float(usage.get("cost") or 0.0),
            }
        )
        logger.info(
            "vlm_described",
            model=description.model,
            item=description.item,
            parsed=description.parsed,
            latency_ms=description.latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=description.cost_usd,
        )

        self._cache[key] = description
        if len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)
        return description
