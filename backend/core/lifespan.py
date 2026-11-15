"""Application lifespan events — startup and shutdown."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging

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

    async with app.state.mcp_sessions.run():  # a mounted app's own lifespan never runs, so the host enters it
        yield

    # --- Shutdown ---
    from backend.core.tracing import get_tracer

    get_tracer().shutdown()
    logger.info("app_stopped")
