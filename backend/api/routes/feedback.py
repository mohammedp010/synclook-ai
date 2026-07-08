"""Feedback endpoint — users can like/dislike recommendations."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_feedback_service
from backend.core.logging import get_logger
from backend.core.rate_limit import limiter
from backend.db.session import get_db_session
from backend.schemas.api import FeedbackRequest, FeedbackResponse
from backend.services.feedback import FeedbackService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db_session),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> FeedbackResponse:
    """Record user feedback (like/dislike) on a recommendation.

    Persists to PostgreSQL and updates user preferences in Redis.
    """
    logger.info(
        "feedback_received",
        request_id=str(body.request_id),
        recommendation_id=str(body.recommendation_id),
        feedback=body.feedback.value,
        user_id=body.user_id,
    )

    await feedback_svc.record_feedback(
        db,
        request_id=body.request_id,
        recommendation_id=body.recommendation_id,
        feedback=body.feedback.value,
        user_id=body.user_id,
        comment=body.comment,
    )

    return FeedbackResponse(message="Feedback recorded")
