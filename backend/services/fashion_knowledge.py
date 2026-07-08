"""Fashion knowledge service backed by a JSON knowledge base.

Provides deterministic clothing compatibility knowledge independent of LLMs.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.core.logging import get_logger
from backend.schemas.clothing import ClothingType

logger = get_logger(__name__)


def _shopping_intent_to_knowledge_key(value: str) -> str:
    normalized = (value or "unisex").strip().lower()
    return {
        "menswear": "male",
        "male": "male",
        "womenswear": "female",
        "female": "female",
        "all": "unisex",
        "unisex": "unisex",
    }.get(normalized, "unisex")


class FashionKnowledgeService:
    """Read-only domain knowledge for category and pairing constraints."""

    def __init__(self, knowledge_path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "data" / "fashion_knowledge.json"
        self._knowledge_path = knowledge_path or default_path
        self._knowledge = self._load_knowledge()

    @staticmethod
    def normalize_item_name(item_name: str) -> str:
        return (item_name or "").strip().lower().replace("_", "-")

    @staticmethod
    def _normalize_style(style_name: str | None) -> str:
        return (style_name or "").strip().lower()

    @staticmethod
    def _to_clothing_type(item_name: str) -> ClothingType | None:
        normalized = FashionKnowledgeService.normalize_item_name(item_name)
        for ct in ClothingType:
            if ct.value == normalized:
                return ct
        return None

    def _load_knowledge(self) -> dict:
        try:
            raw = self._knowledge_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                logger.warning("fashion_knowledge_invalid", reason="root_not_dict")
                return {}
            return data
        except FileNotFoundError:
            logger.warning("fashion_knowledge_missing", path=str(self._knowledge_path))
            return {}
        except json.JSONDecodeError as exc:
            logger.warning("fashion_knowledge_json_error", error=str(exc))
            return {}

    def _entry(self, item_type: ClothingType | str) -> dict:
        if isinstance(item_type, ClothingType):
            key = item_type.value
        else:
            key = self.normalize_item_name(item_type)
        entry = self._knowledge.get(key, {})
        return entry if isinstance(entry, dict) else {}

    def get_category(self, item_type: ClothingType | str) -> str | None:
        entry = self._entry(item_type)
        category = entry.get("category")
        return category if isinstance(category, str) else None

    def get_avoid_items(self, item_type: ClothingType | str, gender: str = "unisex") -> list[str]:
        entry = self._entry(item_type)
        avoid = entry.get("avoid", {})
        if not isinstance(avoid, dict):
            return []

        gender_key = _shopping_intent_to_knowledge_key(gender)
        gender_items = avoid.get(gender_key, [])
        global_items = avoid.get("all", [])

        merged = []
        for item in [*global_items, *gender_items]:
            if not isinstance(item, str):
                continue
            normalized = self.normalize_item_name(item)
            if normalized and normalized not in merged:
                merged.append(normalized)
        return merged

    def get_best_matches(
        self,
        item_type: ClothingType | str,
        *,
        style: str | None = None,
        gender: str = "unisex",
    ) -> list[str]:
        entry = self._entry(item_type)
        if not entry:
            return []

        style_key = self._normalize_style(style)
        style_map = entry.get("styles", {})
        style_matches: list[str] = []
        if isinstance(style_map, dict) and style_key in style_map:
            style_data = style_map.get(style_key, [])
            if isinstance(style_data, list):
                style_matches = [s for s in style_data if isinstance(s, str)]

        base_matches = entry.get("best_matches", [])
        if not isinstance(base_matches, list):
            base_matches = []

        ordered = style_matches if style_matches else [s for s in base_matches if isinstance(s, str)]
        avoid_items = set(self.get_avoid_items(item_type, gender=gender))

        cleaned: list[str] = []
        for item in ordered:
            normalized = self.normalize_item_name(item)
            if not normalized or normalized in avoid_items:
                continue
            if normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def is_forbidden_pair(
        self,
        *,
        base_item: ClothingType | str,
        candidate_item: ClothingType | str,
        gender: str = "unisex",
    ) -> bool:
        if isinstance(candidate_item, ClothingType):
            candidate = candidate_item.value
        else:
            candidate = self.normalize_item_name(candidate_item)
        return candidate in set(self.get_avoid_items(base_item, gender=gender))

    def to_clothing_types(self, item_names: list[str]) -> list[ClothingType]:
        result: list[ClothingType] = []
        seen: set[ClothingType] = set()
        for name in item_names:
            ct = self._to_clothing_type(name)
            if ct is None or ct in seen:
                continue
            result.append(ct)
            seen.add(ct)
        return result
