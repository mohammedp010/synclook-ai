"""Application lifespan events — startup and shutdown."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.db.redis import close_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    settings = get_settings()

    # --- Startup ---
    setup_logging(settings.log_level)
    logger.info(
        "app_starting",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

    # Ensure upload directory exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    yield

    # --- Shutdown ---
    # Close memory service if created via DI
    from backend.core.dependencies import get_memory_service

    try:
        memory = get_memory_service()
        await memory.close()
    except Exception:
        pass

    await close_redis()
    logger.info("app_stopped")
