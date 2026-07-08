"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.core.config import get_settings
from backend.core.lifespan import lifespan
from backend.core.rate_limit import limiter
from backend.api.routes import health, analysis, feedback, stream


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Rate Limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- Routes ---
    app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
    app.include_router(analysis.router, prefix=settings.api_prefix, tags=["analysis"])
    app.include_router(feedback.router, prefix=settings.api_prefix, tags=["feedback"])
    app.include_router(stream.router, prefix=settings.api_prefix, tags=["streaming"])

    return app
