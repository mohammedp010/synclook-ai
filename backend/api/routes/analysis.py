"""Image upload and clothing analysis endpoint."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.orchestrator import Orchestrator
from backend.core.config import get_settings
from backend.core.dependencies import get_feedback_service, get_orchestrator
from backend.core.exceptions import ImageProcessingError, raise_bad_request
from backend.core.logging import get_logger
from backend.core.rate_limit import limiter
from backend.db.session import get_db_session
from backend.schemas.api import AnalysisResponse, Gender, ShoppingIntent
from backend.services.feedback import FeedbackService

router = APIRouter()
logger = get_logger(__name__)


@router.post("/analyze", response_model=AnalysisResponse)
@limiter.limit("10/minute")
async def analyze_clothing(
    request: Request,
    image: UploadFile = File(...),
    user_id: str | None = None,
    gender: Gender = Gender.UNISEX,
    shopping_intent: ShoppingIntent | None = None,
    include_products: bool = True,
    user_intent: str | None = None,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    feedback_svc: FeedbackService = Depends(get_feedback_service),
) -> AnalysisResponse:
    """Upload a clothing image for analysis and outfit recommendation.

    The orchestrator chains all agents:
    1. Validate image
    2. VisionAgent → extract attributes via CLIP + BLIP
    3. StylingAgent → apply color/style/pattern rules
    4. RecommendationAgent → generate outfit suggestions
    5. ShoppingAgent → attach real product links (optional)
    6. Persist analysis to PostgreSQL
    """
    settings = get_settings()

    # --- Validate upload ---
    if image.content_type not in settings.allowed_image_types:
        raise_bad_request(f"Unsupported image type '{image.content_type}'. Allowed: {settings.allowed_image_types}")

    contents = await image.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise_bad_request(f"Image exceeds maximum size of {settings.max_upload_size_mb} MB")

    logger.info(
        "analysis_requested",
        user_id=user_id,
        filename=image.filename,
        size_bytes=len(contents),
        content_type=image.content_type,
    )

    # --- Full agent pipeline via orchestrator ---
    try:
        ctx = await orchestrator.run(
            contents,
            user_id=user_id,
            gender=gender.value,
            shopping_intent=shopping_intent.value if shopping_intent else None,
            include_products=include_products,
            user_intent=user_intent,
        )
    except ImageProcessingError:
        raise
    except Exception as exc:
        logger.error("analysis_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image analysis failed due to an internal server error",
        ) from exc

    response = AnalysisResponse(
        request_id=ctx.request_id,
        detected_attributes=ctx.clothing_attributes,  # type: ignore[arg-type]
        recommendations=ctx.recommendations,
    )

    # --- Persist analysis to DB ---
    try:
        await feedback_svc.save_analysis(
            db,
            request_id=ctx.request_id,
            user_id=user_id,
            image_path=image.filename or "unknown",
            detected_attributes=ctx.clothing_attributes.model_dump(mode="json"),  # type: ignore[union-attr]
            recommendations=ctx.recommendations,
        )
    except Exception as exc:
        logger.warning("analysis_persist_failed", error=str(exc))
        # Leave the session usable — the dependency commits on exit.
        await db.rollback()

    return response
