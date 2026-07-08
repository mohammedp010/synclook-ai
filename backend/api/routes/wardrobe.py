"""Digital-closet CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.dependencies import get_wardrobe_service
from backend.core.exceptions import raise_bad_request
from backend.core.logging import get_logger
from backend.core.rate_limit import limiter
from backend.db.session import get_db_session
from backend.models.records import WardrobeItem
from backend.services.wardrobe import WardrobeService

router = APIRouter()
logger = get_logger(__name__)


class WardrobeItemResponse(BaseModel):
    """A wardrobe item as returned by the API (embedding stays internal)."""

    id: uuid.UUID
    label: str
    clothing_type: str
    color: str
    pattern: str
    style: str
    created_at: datetime | None = None


class WardrobeItemUpdate(BaseModel):
    """Manual tag corrections — supervised feedback on the vision tags."""

    label: str | None = None
    clothing_type: str | None = None
    color: str | None = None
    pattern: str | None = None
    style: str | None = None


def _to_response(item: WardrobeItem) -> WardrobeItemResponse:
    return WardrobeItemResponse(
        id=item.id,
        label=item.label,
        clothing_type=item.clothing_type,
        color=item.color,
        pattern=item.pattern,
        style=item.style,
        created_at=item.created_at,
    )


@router.post("/wardrobe/items", response_model=WardrobeItemResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def add_wardrobe_item(
    request: Request,
    user_id: str,
    image: UploadFile = File(...),
    label: str = "",
    wardrobe: WardrobeService = Depends(get_wardrobe_service),
    db: AsyncSession = Depends(get_db_session),
) -> WardrobeItemResponse:
    """Upload a garment photo; it is auto-tagged and added to the closet."""
    settings = get_settings()
    if image.content_type not in settings.allowed_image_types:
        raise_bad_request(f"Unsupported image type '{image.content_type}'")
    contents = await image.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise_bad_request(f"Image exceeds maximum size of {settings.max_upload_size_mb} MB")

    item = await wardrobe.add_item(db, user_id=user_id, image_bytes=contents, label=label)
    return _to_response(item)


@router.get("/wardrobe/items", response_model=list[WardrobeItemResponse])
async def list_wardrobe_items(
    user_id: str,
    wardrobe: WardrobeService = Depends(get_wardrobe_service),
    db: AsyncSession = Depends(get_db_session),
) -> list[WardrobeItemResponse]:
    items = await wardrobe.list_items(db, user_id)
    return [_to_response(item) for item in items]


@router.patch("/wardrobe/items/{item_id}", response_model=WardrobeItemResponse)
async def update_wardrobe_item(
    item_id: uuid.UUID,
    user_id: str,
    update: WardrobeItemUpdate,
    wardrobe: WardrobeService = Depends(get_wardrobe_service),
    db: AsyncSession = Depends(get_db_session),
) -> WardrobeItemResponse:
    fields = {k: v for k, v in update.model_dump().items() if v is not None}
    item = await wardrobe.update_item(db, user_id=user_id, item_id=item_id, **fields)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item not found")
    return _to_response(item)


@router.delete("/wardrobe/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wardrobe_item(
    item_id: uuid.UUID,
    user_id: str,
    wardrobe: WardrobeService = Depends(get_wardrobe_service),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await wardrobe.delete_item(db, user_id=user_id, item_id=item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wardrobe item not found")
