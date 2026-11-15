"""Dependency injection — reusable FastAPI dependencies."""

from functools import lru_cache

from backend.services.cache import KvCache
from backend.services.llm import LLMService
from backend.services.perception import Perceiver
from backend.services.product_judge import ProductJudge
from backend.services.product_search import ProductSearchService
from backend.services.weather import WeatherService
from backend.tools.product_search import ProductSearchTool


@lru_cache
def get_llm_service() -> LLMService:
    """Singleton LLMService instance."""
    return LLMService()


@lru_cache
def get_product_search_service() -> ProductSearchService:
    """Singleton ProductSearchService instance."""
    return ProductSearchService()


@lru_cache
def get_cache() -> KvCache:
    """Singleton KvCache over the app's Postgres session factory."""
    return KvCache()


def get_product_search_tool() -> ProductSearchTool:
    """ProductSearchTool backed by the kv_cache."""
    return ProductSearchTool(get_product_search_service(), get_cache())


@lru_cache
def get_product_judge() -> ProductJudge:
    """The Jev product gate (held-out F1 0.946)."""
    return ProductJudge()


@lru_cache
def get_perceiver() -> Perceiver:
    """Describe → judge perception, cached in kv_cache by image hash."""
    return Perceiver(cache=get_cache())


@lru_cache
def get_weather_service() -> WeatherService:
    return WeatherService(cache=get_cache())
