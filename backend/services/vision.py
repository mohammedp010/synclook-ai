"""Vision service — CLIP zero-shot classification + optional BLIP captioning.

Efficiency contract:

- The CLIP image embedding is computed **once** per request and shared by all
  four attribute heads (type / color / pattern / style).
- Text prompt embeddings are constant, so they are computed once per process
  and cached; each attribute head then costs a single matrix multiply.
- BLIP captioning is optional (``vision_enable_caption``); when disabled the
  ~1GB BLIP model is never loaded.

The normalized image embedding is returned alongside the attributes so
downstream stages (product reranking, wardrobe search) can reuse it without
another forward pass.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from io import BytesIO
from threading import Lock

import torch
from PIL import Image
from transformers import (
    BlipForConditionalGeneration,
    BlipProcessor,
    CLIPModel,
    CLIPProcessor,
)

from backend.core.config import get_settings
from backend.core.exceptions import ImageProcessingError
from backend.core.logging import get_logger
from backend.schemas.clothing import (
    ClothingAttributes,
    ClothingType,
    Color,
    Pattern,
    Style,
)

logger = get_logger(__name__)

# Single thread pool for model inference — avoids OOM with parallel requests.
_inference_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vision")

# ──────────────────────────────────────────────────────────────────────
#  Prompt templates for CLIP zero-shot classification
# ──────────────────────────────────────────────────────────────────────

_CLOTHING_TYPE_PROMPTS: dict[ClothingType, list[str]] = {
    ClothingType.TSHIRT: ["a t-shirt", "a tee shirt"],
    ClothingType.SHIRT: ["a button-up shirt", "a dress shirt", "a collared shirt"],
    ClothingType.BLOUSE: ["a blouse", "a women's blouse"],
    ClothingType.JACKET: ["a jacket", "an outer jacket"],
    ClothingType.BLAZER: ["a blazer", "a suit blazer"],
    ClothingType.COAT: ["a coat", "an overcoat", "a long coat"],
    ClothingType.SWEATER: ["a sweater", "a knit sweater", "a pullover"],
    ClothingType.HOODIE: ["a hoodie", "a hooded sweatshirt"],
    ClothingType.DRESS: ["a dress", "a women's dress"],
    ClothingType.SKIRT: ["a skirt", "a women's skirt"],
    ClothingType.TROUSERS: ["trousers", "dress pants", "formal trousers"],
    ClothingType.JEANS: ["jeans", "denim jeans", "blue jeans"],
    ClothingType.SHORTS: ["shorts", "short pants"],
    ClothingType.CHINOS: ["chinos", "chino pants", "khaki pants"],
    ClothingType.SUIT: ["a full suit", "a business suit"],
    ClothingType.SHOES: ["shoes", "footwear", "a pair of shoes"],
    ClothingType.ACCESSORY: ["fashion accessory", "belt", "bag", "watch", "scarf"],
    ClothingType.OTHER: ["clothing item", "a garment"],
}

_COLOR_PROMPTS: dict[Color, list[str]] = {c: [f"{c.value} colored clothing"] for c in Color if c != Color.OTHER}
_COLOR_PROMPTS[Color.OTHER] = ["multicolored clothing"]

_PATTERN_PROMPTS: dict[Pattern, list[str]] = {
    Pattern.SOLID: ["solid plain fabric"],
    Pattern.STRIPED: ["striped fabric", "striped pattern"],
    Pattern.CHECKERED: ["checkered fabric", "checked pattern"],
    Pattern.FLORAL: ["floral print", "flower pattern"],
    Pattern.POLKA_DOT: ["polka dot pattern", "dotted fabric"],
    Pattern.PLAID: ["plaid pattern", "tartan fabric"],
    Pattern.ABSTRACT: ["abstract print", "abstract pattern"],
    Pattern.OTHER: ["patterned fabric"],
}

_STYLE_PROMPTS: dict[Style, list[str]] = {
    Style.FORMAL: ["formal wear", "business attire", "formal clothing"],
    Style.CASUAL: ["casual wear", "everyday clothing", "casual outfit"],
    Style.SMART_CASUAL: ["smart casual outfit", "semi-formal clothing"],
    Style.STREETWEAR: ["streetwear", "urban street fashion"],
    Style.SPORTY: ["sportswear", "athletic clothing", "activewear"],
    Style.BOHEMIAN: ["bohemian style", "boho fashion"],
    Style.MINIMALIST: ["minimalist clothing", "simple clean outfit"],
    Style.OTHER: ["clothing"],
}


@dataclass
class VisionResult:
    """Full output of the vision pipeline.

    ``image_embedding`` is the L2-normalized CLIP image embedding — reusable
    for similarity search (product reranking, wardrobe matching) without
    another forward pass.
    """

    attributes: ClothingAttributes
    image_embedding: list[float]


# ──────────────────────────────────────────────────────────────────────
#  Model loader (singleton)
# ──────────────────────────────────────────────────────────────────────


class _ModelHolder:
    """Lazy-loaded singleton for CLIP and BLIP models + cached text features."""

    def __init__(self) -> None:
        self._clip_model: CLIPModel | None = None
        self._clip_processor: CLIPProcessor | None = None
        self._blip_model: BlipForConditionalGeneration | None = None
        self._blip_processor: BlipProcessor | None = None
        self._device: torch.device | None = None
        self._logit_scale: float | None = None
        self._text_features: dict[str, tuple[torch.Tensor, list[str]]] = {}
        self._lock = Lock()

    @property
    def device(self) -> torch.device:
        if self._device is None:
            settings = get_settings()
            self._device = torch.device(settings.vision_device)
        return self._device

    def _load_clip(self) -> tuple[CLIPModel, CLIPProcessor]:
        with self._lock:
            if self._clip_model is None:
                settings = get_settings()
                logger.info("loading_clip_model", model=settings.clip_model_name)
                self._clip_processor = CLIPProcessor.from_pretrained(settings.clip_model_name)
                model = CLIPModel.from_pretrained(settings.clip_model_name)
                self._clip_model = model.to(self.device)  # type: ignore[arg-type]
                self._clip_model.eval()
                self._logit_scale = float(self._clip_model.logit_scale.exp().item())
                logger.info("clip_model_loaded", logit_scale=self._logit_scale)
        assert self._clip_model is not None
        assert self._clip_processor is not None
        return self._clip_model, self._clip_processor

    def _load_blip(self) -> tuple[BlipForConditionalGeneration, BlipProcessor]:
        with self._lock:
            if self._blip_model is None:
                settings = get_settings()
                logger.info("loading_blip_model", model=settings.blip_model_name)
                self._blip_processor = BlipProcessor.from_pretrained(settings.blip_model_name)
                model = BlipForConditionalGeneration.from_pretrained(settings.blip_model_name)
                self._blip_model = model.to(self.device)  # type: ignore[arg-type]
                self._blip_model.eval()
                logger.info("blip_model_loaded")
        assert self._blip_model is not None
        assert self._blip_processor is not None
        return self._blip_model, self._blip_processor

    @property
    def clip(self) -> tuple[CLIPModel, CLIPProcessor]:
        return self._load_clip()

    @property
    def blip(self) -> tuple[BlipForConditionalGeneration, BlipProcessor]:
        return self._load_blip()

    @property
    def logit_scale(self) -> float:
        self._load_clip()
        assert self._logit_scale is not None
        return self._logit_scale

    def text_features[E: Enum](self, head: str, prompts_map: dict[E, list[str]]) -> tuple[torch.Tensor, list[str]]:
        """Return (normalized text embeddings, per-prompt enum labels) for a head.

        Computed once per process — prompts are constants, so re-encoding them
        on every request (as the previous implementation did) was pure waste.
        """
        cached = self._text_features.get(head)
        if cached is not None:
            return cached

        model, processor = self.clip
        all_prompts: list[str] = []
        labels: list[str] = []
        for member, texts in prompts_map.items():
            for text in texts:
                all_prompts.append(text)
                labels.append(member.value)

        inputs = processor(text=all_prompts, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            # transformers v5: projected embeddings live in .pooler_output
            features: torch.Tensor = model.get_text_features(**inputs).pooler_output
        features = features / features.norm(dim=-1, keepdim=True)

        with self._lock:
            self._text_features[head] = (features, labels)
        logger.info("text_features_cached", head=head, num_prompts=len(all_prompts))
        return features, labels


@lru_cache
def _get_models() -> _ModelHolder:
    return _ModelHolder()


# ──────────────────────────────────────────────────────────────────────
#  Core inference helpers (synchronous — run in thread pool)
# ──────────────────────────────────────────────────────────────────────


def _open_image(image_bytes: bytes) -> Image.Image:
    """Open and convert raw bytes to an RGB PIL Image."""
    try:
        img = Image.open(BytesIO(image_bytes))
        return img.convert("RGB")
    except Exception as exc:
        raise ImageProcessingError(f"Cannot decode image: {exc}") from exc


def _center_crop(image: Image.Image, ratio: float) -> Image.Image:
    """Lightweight center crop to reduce background scene noise.

    ``ratio`` is clamped to [0.4, 1.0] to avoid over-cropping.
    """
    clamped = max(0.4, min(float(ratio), 1.0))
    if clamped >= 0.999:
        return image

    width, height = image.size
    crop_w = max(1, int(width * clamped))
    crop_h = max(1, int(height * clamped))
    left = (width - crop_w) // 2
    top = (height - crop_h) // 2
    right = left + crop_w
    bottom = top + crop_h
    return image.crop((left, top, right, bottom))


def _encode_image(image: Image.Image, holder: _ModelHolder) -> torch.Tensor:
    """Encode an image into a normalized CLIP embedding (single forward pass)."""
    model, processor = holder.clip
    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(holder.device) for k, v in inputs.items()}
    with torch.no_grad():
        # transformers v5: projected embeddings live in .pooler_output
        features: torch.Tensor = model.get_image_features(**inputs).pooler_output
    features = features / features.norm(dim=-1, keepdim=True)
    return features[0]


def _classify_head[E: Enum](
    image_features: torch.Tensor,
    head: str,
    prompts_map: dict[E, list[str]],
    holder: _ModelHolder,
) -> tuple[str, float]:
    """Zero-shot classify one attribute head against a precomputed image embedding.

    Returns (best_label, confidence). Confidence is the softmax probability of
    the winning prompt (max across a label's prompt variants), matching the
    semantics of the previous per-head implementation.
    """
    text_features, labels = holder.text_features(head, prompts_map)
    logits = holder.logit_scale * (text_features @ image_features)
    probs = logits.softmax(dim=0)

    label_scores: dict[str, float] = {}
    for prob, label in zip(probs.tolist(), labels):
        if label not in label_scores or prob > label_scores[label]:
            label_scores[label] = prob

    best_label = max(label_scores, key=lambda k: label_scores[k])
    return best_label, label_scores[best_label]


def _blip_caption(image: Image.Image, holder: _ModelHolder) -> str:
    """Generate a text caption for the image using BLIP."""
    model, processor = holder.blip

    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(holder.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=64)

    caption: str = processor.decode(output_ids[0], skip_special_tokens=True)  # type: ignore[no-untyped-call]
    return caption.strip()


def _is_caption_relevant(
    caption: str,
    clothing_type: ClothingType,
    color: Color,
) -> bool:
    """Lightweight lexical relevance check for scene captions."""
    text = (caption or "").strip().lower()
    if not text:
        return False

    item_tokens = {
        clothing_type.value,
        clothing_type.value.replace("-", " "),
    }
    alias_map = {
        ClothingType.TROUSERS: {"pants", "trousers", "slacks"},
        ClothingType.TSHIRT: {"t-shirt", "tshirt", "tee", "shirt"},
        ClothingType.SHIRT: {"shirt"},
        ClothingType.HOODIE: {"hoodie", "hooded"},
        ClothingType.SWEATER: {"sweater", "pullover"},
        ClothingType.JEANS: {"jeans", "denim"},
        ClothingType.SHOES: {"shoes", "footwear", "sneakers", "boots", "loafers"},
        ClothingType.ACCESSORY: {"accessory", "belt", "bag", "watch", "scarf"},
    }
    item_tokens.update(alias_map.get(clothing_type, set()))

    color_tokens = {color.value}
    if color == Color.GREY:
        color_tokens.add("gray")

    has_item = any(token in text for token in item_tokens)
    has_color = any(token in text for token in color_tokens)
    return has_item or has_color


def _run_vision_pipeline(image_bytes: bytes) -> VisionResult:
    """Full synchronous vision pipeline — called inside the thread pool."""
    settings = get_settings()
    holder = _get_models()
    image = _open_image(image_bytes)

    if settings.vision_use_center_crop:
        image = _center_crop(image, settings.vision_center_crop_ratio)

    # One image encoding shared by all four attribute heads.
    image_features = _encode_image(image, holder)

    clothing_type_val, type_conf = _classify_head(image_features, "clothing_type", _CLOTHING_TYPE_PROMPTS, holder)
    color_val, color_conf = _classify_head(image_features, "color", _COLOR_PROMPTS, holder)
    pattern_val, pattern_conf = _classify_head(image_features, "pattern", _PATTERN_PROMPTS, holder)
    style_val, style_conf = _classify_head(image_features, "style", _STYLE_PROMPTS, holder)

    clothing_type = ClothingType(clothing_type_val)
    primary_color = Color(color_val)

    # Optional BLIP caption (display metadata only; never used for decisions).
    caption = ""
    caption_relevant = False
    if settings.vision_enable_caption:
        caption = _blip_caption(image, holder)
        caption_relevant = _is_caption_relevant(caption, clothing_type, primary_color)

    attributes = ClothingAttributes(
        clothing_type=clothing_type,
        primary_color=primary_color,
        pattern=Pattern(pattern_val),
        style=Style(style_val),
        confidence=round(type_conf, 3),
        color_confidence=round(color_conf, 3),
        pattern_confidence=round(pattern_conf, 3),
        style_confidence=round(style_conf, 3),
        description=caption,
        description_relevant=caption_relevant,
    )

    logger.info(
        "vision_pipeline_complete",
        clothing_type=attributes.clothing_type.value,
        color=attributes.primary_color.value,
        pattern=attributes.pattern.value,
        style=attributes.style.value,
        confidence=attributes.confidence,
        color_confidence=attributes.color_confidence,
        pattern_confidence=attributes.pattern_confidence,
        style_confidence=attributes.style_confidence,
    )

    return VisionResult(attributes=attributes, image_embedding=image_features.tolist())


# ──────────────────────────────────────────────────────────────────────
#  Public async API
# ──────────────────────────────────────────────────────────────────────


class VisionService:
    """Async facade over the CLIP (+ optional BLIP) vision pipeline."""

    async def analyze_image(self, image_bytes: bytes) -> VisionResult:
        """Analyze a clothing image; returns attributes plus the CLIP embedding.

        Runs model inference in a thread pool to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_inference_pool, _run_vision_pipeline, image_bytes)
        except ImageProcessingError:
            raise
        except Exception as exc:
            logger.error("vision_pipeline_error", error=str(exc))
            raise ImageProcessingError(f"Vision pipeline failed: {exc}") from exc

    async def warmup(self) -> None:
        """Pre-load models and text-feature caches at startup.

        Avoids cold-start latency on the first request; BLIP is only loaded
        when captioning is enabled.
        """
        loop = asyncio.get_running_loop()
        settings = get_settings()

        def _load() -> None:
            holder = _get_models()
            holder.clip
            holder.text_features("clothing_type", _CLOTHING_TYPE_PROMPTS)
            holder.text_features("color", _COLOR_PROMPTS)
            holder.text_features("pattern", _PATTERN_PROMPTS)
            holder.text_features("style", _STYLE_PROMPTS)
            if settings.vision_enable_caption:
                holder.blip

        await loop.run_in_executor(_inference_pool, _load)
        logger.info("vision_models_warmed_up", caption_enabled=settings.vision_enable_caption)
