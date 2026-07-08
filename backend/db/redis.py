"""Redis client for memory/session management."""

import redis.asyncio as redis

from backend.core.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create the Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info("redis_connected", url=settings.redis_url)
    return _redis_pool


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("redis_disconnected")
