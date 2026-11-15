"""The closet: add a garment photo, list, correct, delete, see its photo, or copy the demo closet."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import budget
from backend.core.config import get_settings
from backend.core.dependencies import get_cache, get_perceiver
from backend.core.rate_limit import limiter
from backend.db.session import get_db_session
from backend.engine.preferences import wear_stats
from backend.models.records import WardrobeItem
from backend.schemas.api import ClosetItemOut, ClosetItemPatch, ClosetStatsOut, DemoClosetOut, ItemWearOut, McpKeyOut
from backend.services import closet, wear
from backend.services.cache import KvCache
from backend.services.perception import Perceiver, PerceptionError

router = APIRouter(prefix="/closet")

UserId = Annotated[str, Header(alias="X-User-Id", min_length=1, max_length=128, description="Opaque closet id")]
Db = Annotated[AsyncSession, Depends(get_db_session)]
Cache = Annotated[KvCache, Depends(get_cache)]


def image_url(item_id: uuid.UUID | str) -> str:
    return f"{get_settings().api_prefix}/closet/items/{item_id}/image"


def item_out(row: WardrobeItem) -> ClosetItemOut:
    return ClosetItemOut(id=row.id, image_url=image_url(row.id), **closet.tags_of(row).model_dump())


async def _owned(db: AsyncSession, user_id: str, item_id: uuid.UUID) -> WardrobeItem:
    row = await closet.get(db, user_id, item_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item in this closet")
    return row


@router.post("/items", status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().paid_rate_limit)
async def add_item(
    request: Request,
    user_id: UserId,
    db: Db,
    cache: Cache,
    file: UploadFile,
    perceiver: Annotated[Perceiver, Depends(get_perceiver)],
) -> ClosetItemOut:
    """Photo → describe (vision model) → judge (Jev) → tags → saved. Costs 1 vision + 1 Jev call.

    The free checks (type, size, closet full, duplicate photo) run first, then the daily upload cap.
    """
    settings = get_settings()
    if file.content_type not in settings.allowed_image_types:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Send one of {settings.allowed_image_types}")
    data = await file.read(settings.max_upload_size_bytes + 1)
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Photos must be under {settings.max_upload_size_mb} MB")
    digest = closet.image_hash(data)
    try:
        await closet.check_can_add(db, user_id, digest)
    except (closet.ClosetFullError, closet.DuplicatePhotoError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await budget.spend(cache, "photo_uploads", settings.upload_daily_cap)
    try:
        tags = await perceiver.perceive(data)
    except PerceptionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    row = await closet.add(db, user_id, tags, data, digest)
    try:
        await db.commit()
    except IntegrityError as exc:  # the same photo uploaded twice at once
        raise HTTPException(status.HTTP_409_CONFLICT, "This photo is already in your closet") from exc
    return item_out(row)


@router.get("/items")
async def list_items(user_id: UserId, db: Db) -> list[ClosetItemOut]:
    return [item_out(row) for row in await closet.list_items(db, user_id)]


@router.patch("/items/{item_id}")
async def correct_item(user_id: UserId, db: Db, item_id: uuid.UUID, patch: ClosetItemPatch) -> ClosetItemOut:
    row = await closet.update(db, await _owned(db, user_id, item_id), patch.model_dump(exclude_unset=True))
    await db.commit()
    return item_out(row)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(user_id: UserId, db: Db, item_id: uuid.UUID) -> None:
    if not await closet.remove(db, user_id, item_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item in this closet")
    await db.commit()


@router.get("/items/{item_id}/image")
async def item_image(db: Db, item_id: uuid.UUID) -> Response:
    # shortcut: no X-User-Id here so an <img> tag can load it; the random UUID is the access key.
    # Require the header (or a signed URL) once closets hold anything private.
    row = await db.get(WardrobeItem, item_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such item")
    return Response(row.image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/demo")
async def copy_demo(user_id: UserId, db: Db) -> DemoClosetOut:
    """Start here: copy the ready-made demo closet (27 items) into this closet. No model calls; safe to repeat."""
    added = await closet.copy_demo(db, user_id)
    await db.commit()
    return DemoClosetOut(added=added, total=await closet.count(db, user_id))


@router.get("/stats")
async def stats(user_id: UserId, db: Db) -> ClosetStatsOut:
    """Times worn and last worn day per item, from the wear log."""
    rows = await closet.list_items(db, user_id)
    counts = wear_stats(await wear.events(db, user_id), [str(r.id) for r in rows])
    items = [
        ItemWearOut(id=r.id, short_label=r.short_label, **vars(counts[str(r.id)]))
        for r in sorted(rows, key=lambda r: -counts[str(r.id)].times_worn)
    ]
    return ClosetStatsOut(items=items, never_worn=[i.id for i in items if i.times_worn == 0])


@router.post("/mcp-key")
async def mcp_key(user_id: UserId, db: Db, request: Request) -> McpKeyOut:
    """A new private MCP URL for this closet, so Claude or ChatGPT can use its tools. The old URL stops working."""
    key = await closet.new_mcp_key(db, user_id)
    await db.commit()
    return McpKeyOut(url=f"{str(request.base_url).rstrip('/')}{get_settings().api_prefix}/mcp/{key}/")
