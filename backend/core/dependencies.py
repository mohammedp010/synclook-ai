"""Dependency injection — reusable FastAPI dependencies."""

from functools import lru_cache

from backend.agents.orchestrator import Orchestrator
from backend.agents.recommendation_agent import RecommendationAgent
from backend.agents.styling_agent import StylingAgent
from backend.agents.vision_agent import VisionAgent
from backend.db.redis import get_redis
from backend.services.fashion_knowledge import FashionKnowledgeService
from backend.services.feedback import FeedbackService
from backend.services.llm import LLMService
from backend.services.memory import MemoryService
from backend.services.product_search import ProductSearchService
from backend.services.vision import VisionService
from backend.services.wardrobe import WardrobeService
from backend.tools.product_search import ProductSearchTool


@lru_cache
def get_vision_service() -> VisionService:
    """Singleton VisionService instance."""
    return VisionService()


@lru_cache
def get_llm_service() -> LLMService:
    """Singleton LLMService instance."""
    return LLMService()


@lru_cache
def get_memory_service() -> MemoryService:
    """Singleton MemoryService instance."""
    return MemoryService()


@lru_cache
def get_fashion_knowledge_service() -> FashionKnowledgeService:
    """Singleton FashionKnowledgeService instance."""
    return FashionKnowledgeService()


@lru_cache
def get_product_search_service() -> ProductSearchService:
    """Singleton ProductSearchService instance."""
    return ProductSearchService()


async def get_product_search_tool() -> ProductSearchTool:
    """ProductSearchTool — requires async Redis client."""
    redis_client = await get_redis()
    return ProductSearchTool(get_product_search_service(), redis_client)


@lru_cache
def get_vision_agent() -> VisionAgent:
    """Singleton VisionAgent — wraps VisionService."""
    return VisionAgent(get_vision_service())


@lru_cache
def get_styling_agent() -> StylingAgent:
    """Singleton StylingAgent — rule-based engine."""
    return StylingAgent(fashion_knowledge=get_fashion_knowledge_service())


@lru_cache
def get_recommendation_agent() -> RecommendationAgent:
    """Singleton RecommendationAgent — builds outfit suggestions."""
    return RecommendationAgent(
        llm_service=get_llm_service(),
        fashion_knowledge=get_fashion_knowledge_service(),
    )


async def get_orchestrator() -> Orchestrator:
    """Orchestrator — chains full agent pipeline (async for Redis dep)."""
    product_tool = await get_product_search_tool()
    return Orchestrator(
        get_vision_service(),
        get_llm_service(),
        get_memory_service(),
        product_tool=product_tool,
        fashion_knowledge=get_fashion_knowledge_service(),
    )


@lru_cache
def get_feedback_service() -> FeedbackService:
    """Singleton FeedbackService — feedback persistence + memory updates."""
    return FeedbackService(get_memory_service())


@lru_cache
def get_wardrobe_service() -> WardrobeService:
    """Singleton WardrobeService — digital closet CRUD + matching."""
    return WardrobeService(get_vision_service())
