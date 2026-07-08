"""Unit tests for FashionKnowledgeService."""

from pathlib import Path

from backend.services.fashion_knowledge import FashionKnowledgeService


class TestFashionKnowledgeService:
    def setup_method(self) -> None:
        path = Path(__file__).resolve().parents[2] / "backend" / "data" / "fashion_knowledge.json"
        self.service = FashionKnowledgeService(knowledge_path=path)

    def test_loads_knowledge(self) -> None:
        matches = self.service.get_best_matches("trousers", style="streetwear", gender="male")
        assert matches
        assert "t-shirt" in matches

    def test_avoid_items_respected(self) -> None:
        matches = self.service.get_best_matches("trousers", style="streetwear", gender="male")
        assert "blouse" not in matches

    def test_forbidden_pair(self) -> None:
        assert self.service.is_forbidden_pair(
            base_item="trousers",
            candidate_item="blouse",
            gender="male",
        )

    def test_to_clothing_types(self) -> None:
        items = self.service.to_clothing_types(["t-shirt", "shirt", "unknown-item"])
        values = [i.value for i in items]
        assert values == ["t-shirt", "shirt"]
