"""Admin endpoints — quality/usage metrics.

NOTE: unauthenticated for now, like the rest of the API; token auth for
admin surfaces lands with the auth-hardening phase.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_metrics_service
from backend.db.session import get_db_session
from backend.services.metrics import MetricsService

router = APIRouter()


@router.get("/admin/metrics")
async def get_metrics(
    metrics: MetricsService = Depends(get_metrics_service),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Aggregated quality and usage metrics for dashboards."""
    return await metrics.get_summary(db)
