"""Health check endpoint."""

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.core.rate_limit import limiter
from backend.schemas.api import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
@limiter.exempt  # type: ignore[untyped-decorator]  # the host polls it; slowapi leaves exempt untyped
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(version=settings.app_version)
