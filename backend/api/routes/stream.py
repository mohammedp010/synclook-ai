"""SSE streaming endpoint for real-time analysis progress."""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from backend.agents.orchestrator import Orchestrator
from backend.core.config import get_settings
from backend.core.dependencies import get_orchestrator
from backend.core.exceptions import raise_bad_request
from backend.core.logging import get_logger
from backend.core.rate_limit import limiter
from backend.schemas.api import Gender, ShoppingIntent

router = APIRouter()
logger = get_logger(__name__)


@router.post("/analyze/stream")
@limiter.limit("10/minute")
async def analyze_clothing_stream(
    request: Request,
    image: UploadFile = File(...),
    user_id: str | None = None,
    gender: Gender = Gender.UNISEX,
    shopping_intent: ShoppingIntent | None = None,
    include_products: bool = True,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> EventSourceResponse:
    """Stream clothing analysis progress via Server-Sent Events.

    Emits events: status, agent_done, warning, error, result, done.
    """
    settings = get_settings()

    if image.content_type not in settings.allowed_image_types:
        raise_bad_request(f"Unsupported image type '{image.content_type}'. Allowed: {settings.allowed_image_types}")

    contents = await image.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise_bad_request(f"Image exceeds maximum size of {settings.max_upload_size_mb} MB")

    logger.info(
        "stream_analysis_requested",
        user_id=user_id,
        filename=image.filename,
        size_bytes=len(contents),
    )

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        async for event in orchestrator.run_stream(
            contents,
            user_id=user_id,
            gender=gender.value,
            shopping_intent=shopping_intent.value if shopping_intent else None,
            include_products=include_products,
        ):
            if await request.is_disconnected():
                logger.info("stream_client_disconnected", user_id=user_id)
                break
            yield event

    return EventSourceResponse(event_generator())
