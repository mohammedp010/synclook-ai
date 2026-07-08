"""Vision service — CLIP (zero-shot classification) + BLIP (image captioning).

Models are loaded lazily on first call and reused for the lifetime of the process.
All inference is offloaded to a thread-pool so the async event loop stays free.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    pass

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

_COLOR_PROMPTS: dict[Color, list[str]] = {
    c: [f"{c.value} colored clothing"] for c in Color if c != Color.OTHER
}
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


# ──────────────────────────────────────────────────────────────────────
#  Model loader (singleton)
# ──────────────────────────────────────────────────────────────────────


class _ModelHolder:
    """Lazy-loaded singleton for CLIP and BLIP models."""

    def __init__(self) -> None:
        self._clip_model: CLIPModel | None = None
        self._clip_processor: CLIPProcessor | None = None
        self._blip_model: BlipForConditionalGeneration | None = None
        self._blip_processor: BlipProcessor | None = None
        self._device: torch.device | None = None

    @property
    def device(self) -> torch.device:
        if self._device is None:
            settings = get_settings()
            self._device = torch.device(settings.vision_device)
        return self._device

    def _load_clip(self) -> tuple[CLIPModel, CLIPProcessor]:
        if self._clip_model is None:
            settings = get_settings()
            logger.info("loading_clip_model", model=settings.clip_model_name)
            self._clip_processor = CLIPProcessor.from_pretrained(settings.clip_model_name)
            self._clip_model = CLIPModel.from_pretrained(settings.clip_model_name).to(self.device)
            self._clip_model.eval()
            logger.info("clip_model_loaded")
        assert self._clip_model is not None
        assert self._clip_processor is not None
        return self._clip_model, self._clip_processor

    def _load_blip(self) -> tuple[BlipForConditionalGeneration, BlipProcessor]:
        if self._blip_model is None:
            settings = get_settings()
            logger.info("loading_blip_model", model=settings.blip_model_name)
            self._blip_processor = BlipProcessor.from_pretrained(settings.blip_model_name)
            self._blip_model = BlipForConditionalGeneration.from_pretrained(
                settings.blip_model_name
            ).to(self.device)
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


def _clip_classify(
    image: Image.Image,
    prompts_map: dict,
    holder: _ModelHolder,
) -> tuple[str, float]:
    """Run CLIP zero-shot classification and return (best_label, confidence).

    ``prompts_map`` maps an enum member → list of text prompts.
    The prompt with the highest similarity determines the winning enum member.
    """
    model, processor = holder.clip

    # Flatten prompts and keep track of which enum they belong to
    all_prompts: list[str] = []
    prompt_to_label: list[str] = []
    for enum_member, texts in prompts_map.items():
        for t in texts:
            all_prompts.append(t)
            prompt_to_label.append(enum_member.value if hasattr(enum_member, "value") else str(enum_member))

    inputs = processor(text=all_prompts, images=image, return_tensors="pt", padding=True)
    inputs = {k: v.to(holder.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits_per_image[0]  # shape: (num_prompts,)
    probs = logits.softmax(dim=0)

    # Aggregate probabilities per enum label (max across prompt variants)
    label_scores: dict[str, float] = {}
    for prob, label in zip(probs.tolist(), prompt_to_label):
        if label not in label_scores or prob > label_scores[label]:
            label_scores[label] = prob

    best_label = max(label_scores, key=label_scores.get)  # type: ignore[arg-type]
    return best_label, label_scores[best_label]


def _blip_caption(image: Image.Image, holder: _ModelHolder) -> str:
    """Generate a text caption for the image using BLIP."""
    model, processor = holder.blip

    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(holder.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=64)

    caption: str = processor.decode(output_ids[0], skip_special_tokens=True)
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


def _run_vision_pipeline(image_bytes: bytes) -> ClothingAttributes:
    """Full synchronous vision pipeline — called inside the thread pool."""
    settings = get_settings()
    holder = _get_models()
    image = _open_image(image_bytes)

    if settings.vision_use_center_crop:
        image = _center_crop(image, settings.vision_center_crop_ratio)

    # 1. Classify clothing type
    clothing_type_val, type_conf = _clip_classify(image, _CLOTHING_TYPE_PROMPTS, holder)
    clothing_type = ClothingType(clothing_type_val)

    # 2. Classify primary color
    color_val, color_conf = _clip_classify(image, _COLOR_PROMPTS, holder)
    primary_color = Color(color_val)

    # 3. Classify pattern
    pattern_val, pattern_conf = _clip_classify(image, _PATTERN_PROMPTS, holder)
    pattern = Pattern(pattern_val)

    # 4. Classify style
    style_val, style_conf = _clip_classify(image, _STYLE_PROMPTS, holder)
    style = Style(style_val)

    # 5. Generate BLIP caption (display metadata only; never used for decisions)
    caption = _blip_caption(image, holder)
    caption_relevant = _is_caption_relevant(caption, clothing_type, primary_color)

    # Average confidence across all classification heads
    avg_confidence = round((type_conf + color_conf + pattern_conf + style_conf) / 4, 3)

    attributes = ClothingAttributes(
        clothing_type=clothing_type,
        primary_color=primary_color,
        pattern=pattern,
        style=style,
        confidence=avg_confidence,
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
    )

    return attributes


# ──────────────────────────────────────────────────────────────────────
#  Public async API
# ──────────────────────────────────────────────────────────────────────


class VisionService:
    """Async facade over the CLIP + BLIP vision pipeline."""

    async def analyze_image(self, image_bytes: bytes) -> ClothingAttributes:
        """Analyze a clothing image and return structured attributes.

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
        """Pre-load models at startup (optional — avoids cold-start on first request)."""
        loop = asyncio.get_running_loop()

        def _load() -> None:
            holder = _get_models()
            holder.clip
            holder.blip

        await loop.run_in_executor(_inference_pool, _load)
        logger.info("vision_models_warmed_up")
