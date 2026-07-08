"""Feedback Service — persists feedback to PostgreSQL and updates Redis memory.

Bridges the feedback route with both the database (FeedbackRecord) and
the memory system (MemoryService) so that user preferences are updated
in real time.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.records import AnalysisRecord, FeedbackRecord
from backend.schemas.api import Recommendation
from backend.services.memory import MemoryService

logger = get_logger(__name__)


class FeedbackService:
    """Handles feedback persistence and memory updates."""

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    async def record_feedback(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        recommendation_id: UUID,
        feedback: str,
        user_id: str | None = None,
        comment: str | None = None,
    ) -> FeedbackRecord:
        """Persist feedback to PostgreSQL and update Redis preferences.

        1. Save FeedbackRecord to DB
        2. Look up the original AnalysisRecord to extract colors/styles
        3. Update user preferences in Redis via MemoryService
        """
        # 1. Persist to PostgreSQL
        record = FeedbackRecord(
            request_id=request_id,
            recommendation_id=recommendation_id,
            user_id=user_id,
            feedback=feedback,
            comment=comment,
        )
        db.add(record)
        await db.flush()

        logger.info(
            "feedback_persisted",
            feedback_id=str(record.id),
            request_id=str(request_id),
            recommendation_id=str(recommendation_id),
            feedback=feedback,
        )

        # 2. Feed into memory system if user is identified
        if user_id:
            colors, styles = await self._extract_recommendation_context(
                db, request_id=request_id, recommendation_id=recommendation_id,
            )
            if colors or styles:
                try:
                    await self._memory.record_feedback(
                        user_id,
                        feedback_type=feedback,
                        colors=colors,
                        styles=styles,
                    )
                    logger.info(
                        "feedback_memory_updated",
                        user_id=user_id,
                        colors=colors,
                        styles=styles,
                    )
                except Exception as exc:
                    logger.warning("feedback_memory_failed", error=str(exc))

        return record

    async def _extract_recommendation_context(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        recommendation_id: UUID,
    ) -> tuple[list[str], list[str]]:
        """Look up the AnalysisRecord to find colors/styles for the recommendation."""
        stmt = select(AnalysisRecord).where(AnalysisRecord.id == request_id)
        result = await db.execute(stmt)
        analysis = result.scalar_one_or_none()

        if not analysis or not analysis.recommendations:
            return [], []

        # Find the matching recommendation in the stored JSONB
        rec_id_str = str(recommendation_id)
        recs = analysis.recommendations
        if isinstance(recs, list):
            for rec_data in recs:
                if rec_data.get("id") == rec_id_str:
                    colors = [it.get("color", "") for it in rec_data.get("items", []) if it.get("color")]
                    styles = rec_data.get("style_tags", [])
                    return colors, styles

        return [], []

    async def save_analysis(
        self,
        db: AsyncSession,
        *,
        request_id: UUID,
        user_id: str | None,
        image_path: str,
        detected_attributes: dict,
        recommendations: list,
    ) -> AnalysisRecord:
        """Persist an analysis result to PostgreSQL."""
        # Serialize recommendations (Pydantic models → dicts)
        recs_data = []
        for rec in recommendations:
            if isinstance(rec, Recommendation):
                recs_data.append(rec.model_dump(mode="json"))
            elif isinstance(rec, dict):
                recs_data.append(rec)

        record = AnalysisRecord(
            id=request_id,
            user_id=user_id,
            image_path=image_path,
            detected_attributes=detected_attributes,
            recommendations=recs_data,
        )
        db.add(record)
        await db.flush()

        logger.info(
            "analysis_persisted",
            request_id=str(request_id),
            user_id=user_id,
        )
        return record
