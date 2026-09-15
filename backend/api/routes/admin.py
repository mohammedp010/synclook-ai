"""Admin endpoints — quality/usage metrics and the dashboard that reads them.

NOTE: unauthenticated for now, like the rest of the API; token auth for admin
surfaces lands with the auth-hardening phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_metrics_service
from backend.db.session import get_db_session
from backend.services.metrics import MetricsService

router = APIRouter()

_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard.html"
_METRICS_URL = "/api/v1/admin/metrics"


def _dashboard_html() -> str:
    """The dashboard page, with the metrics URL substituted in.

    A static file and one substitution rather than a template engine: the page
    has exactly one variable, and its data arrives client-side from the same
    JSON endpoint any other consumer would use, so there is only one definition
    of what the metrics are. Read per request — the page is opened by hand a
    few times a day, and caching it only buys a stale dashboard after an edit.
    """
    return _TEMPLATE_PATH.read_text(encoding="utf-8").replace("METRICS_URL", _METRICS_URL)


@router.get("/admin/metrics")
async def get_metrics(
    metrics: MetricsService = Depends(get_metrics_service),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Aggregated quality and usage metrics for dashboards."""
    return await metrics.get_summary(db)


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def get_dashboard() -> HTMLResponse:
    """Human-readable view of `/admin/metrics` — eval trends per suite."""
    return HTMLResponse(_dashboard_html())
