"""FastAPI application factory."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.routing import Mount

from backend import mcp_server
from backend.api.routes import chat, closet, health, outfits, shop, wear
from backend.core.budget import BudgetExceededError, seconds_to_reset
from backend.core.config import get_settings
from backend.core.lifespan import lifespan
from backend.core.rate_limit import limiter
from backend.services.image_guard import UnusableImageError


async def _unusable_image_handler(_request: Request, exc: Exception) -> JSONResponse:
    """The upload guard declined the photo — a 422 the frontend already renders.

    ``detail`` stays a plain sentence because the client shows it verbatim; the
    structured fields ride alongside for a UI that wants to offer a retake button.
    """
    assert isinstance(exc, UnusableImageError)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": exc.message, "guard": exc.decision.outcome.value, "reason": exc.decision.reason},
    )


async def _budget_handler(_request: Request, exc: Exception) -> JSONResponse:
    """A daily cap on paid calls is used up (``core/budget.py``): 429 until midnight UTC."""
    assert isinstance(exc, BudgetExceededError)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": exc.message},
        headers={"Retry-After": str(seconds_to_reset())},
    )


_DESCRIPTION = """A closet that knows what goes with what. To try it here, set any `X-User-Id` (e.g. `demo-you`) and:

1. `POST /api/v1/closet/demo`: copy a ready-made 27-item closet (free).
2. `POST /api/v1/outfits` with `{"occasion": "job_interview"}`: what to wear (rules, then one model call to word it).
3. `POST /api/v1/shop/gaps`: the one thing to buy that adds the most outfits (free), then `POST /api/v1/shop/search`.
4. `POST /api/v1/chat`, or `POST /api/v1/closet/mcp-key` for a URL Claude or ChatGPT can use.

This is a public demo with a small daily budget: paid calls (photo uploads, chat, product search, explanations)
answer 429 once it is spent; outfits and gap suggestions keep working."""


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=_DESCRIPTION,
        lifespan=lifespan,
        # /docs stays on in production: with no frontend yet, Swagger is how a visitor tries the backend.
        docs_url="/docs",
        redoc_url=None,
    )

    # --- Middleware ---
    # No cookies or auth headers are used (the closet id is a plain header), so no credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-User-Id"],
    )
    app.add_middleware(SlowAPIMiddleware)  # settings.rate_limit on every route without its own limit

    @app.middleware("http")
    async def refuse_large_bodies(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """413 before a huge upload is read (the upload route checks the photo's own size again).

        shortcut: a chunked request without Content-Length passes; Starlette then spools it to disk.
        """
        if int(request.headers.get("content-length") or 0) > settings.max_upload_size_bytes + 64 * 1024:
            return JSONResponse(
                {"detail": f"Photos must be under {settings.max_upload_size_mb} MB"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        return await call_next(request)

    # --- Rate Limiting and spend caps ---
    app.state.limiter = limiter
    # slowapi's handler is typed narrower than Starlette's handler protocol.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_exception_handler(BudgetExceededError, _budget_handler)
    app.add_exception_handler(UnusableImageError, _unusable_image_handler)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    # --- Routes ---
    app.include_router(health.router, prefix=settings.api_prefix, tags=["health"])
    app.include_router(closet.router, prefix=settings.api_prefix, tags=["closet"])
    app.include_router(outfits.router, prefix=settings.api_prefix, tags=["outfits"])
    app.include_router(shop.router, prefix=settings.api_prefix, tags=["shop"])
    app.include_router(wear.router, prefix=settings.api_prefix, tags=["wear"])
    app.include_router(chat.router, prefix=settings.api_prefix, tags=["chat"])
    mcp_app, app.state.mcp_sessions = mcp_server.asgi_app()
    app.router.routes.append(Mount(f"{settings.api_prefix}/mcp/{{key}}", app=mcp_app))

    return app
