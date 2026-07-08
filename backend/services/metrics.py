"""Metrics service — quality and usage aggregates for the admin dashboard.

Aggregates what the system already persists (analyses, feedback, wardrobe,
evaluation runs); live traces/costs stay in Langfuse, which is the right tool
for per-request drill-down. This endpoint answers "how is the system doing
over time" from our own data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.records import AnalysisRecord, EvaluationRun, FeedbackRecord, WardrobeItem

logger = get_logger(__name__)


class MetricsService:
    """Read-only aggregates over persisted records."""

    async def get_summary(self, db: AsyncSession) -> dict[str, Any]:
        analyses = await self._analysis_stats(db)
        feedback = await self._feedback_stats(db)
        wardrobe_count = (await db.execute(select(func.count(WardrobeItem.id)))).scalar() or 0
        eval_runs = await self._recent_eval_runs(db)

        return {
            "analyses": analyses,
            "feedback": feedback,
            "wardrobe_items": wardrobe_count,
            "evaluation_runs": eval_runs,
        }

    async def _analysis_stats(self, db: AsyncSession) -> dict[str, Any]:
        confidence = cast(AnalysisRecord.detected_attributes["confidence"].astext, Float)
        row = (
            await db.execute(
                select(
                    func.count(AnalysisRecord.id),
                    func.avg(confidence),
                    func.sum(case((confidence < 0.5, 1), else_=0)),
                )
            )
        ).one()
        total = row[0] or 0
        return {
            "total": total,
            "avg_type_confidence": round(float(row[1]), 4) if row[1] is not None else None,
            "low_confidence_rate": round((row[2] or 0) / total, 4) if total else None,
        }

    async def _feedback_stats(self, db: AsyncSession) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(FeedbackRecord.feedback, func.count(FeedbackRecord.id)).group_by(FeedbackRecord.feedback)
            )
        ).all()
        counts = {feedback: count for feedback, count in rows}
        likes = counts.get("like", 0)
        dislikes = counts.get("dislike", 0)
        total = likes + dislikes
        return {
            "likes": likes,
            "dislikes": dislikes,
            "like_rate": round(likes / total, 4) if total else None,
        }

    async def _recent_eval_runs(self, db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            await db.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit))
        ).scalars()
        return [
            {
                "id": str(run.id),
                "git_sha": run.git_sha,
                "num_cases": run.num_cases,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "metrics": run.metrics,
            }
            for run in rows
        ]
