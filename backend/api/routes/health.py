"""Health check endpoint."""

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.schemas.api import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(version=settings.app_version)
