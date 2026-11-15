"""The closet: one user's ``wardrobe_items`` rows, their photos, and the demo closet.

No login: ``user_id`` is an opaque string the client sends. Every query is scoped
to it, so one visitor can never read or change another's items.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.outfits import ClosetItem
from backend.models.records import McpKey, WardrobeItem
from backend.schemas.perception import GarmentTags
from backend.schemas.taxonomy import COARSE_COLOR, ColorName
from backend.services.perception import category_of

MAX_ITEMS_PER_USER = 60
PHOTO_LONGEST_SIDE = 512
DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_closet"


class ClosetFullError(Exception):
    pass


class DuplicatePhotoError(Exception):
    pass


def image_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def thumbnail_jpeg(image_bytes: bytes) -> bytes:
    """The stored copy: upright, RGB, longest side 512 px, JPEG quality 85 (~30–60 KB)."""
    image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert("RGB")
    image.thumbnail((PHOTO_LONGEST_SIDE, PHOTO_LONGEST_SIDE))
    out = BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()


def tags_of(row: WardrobeItem) -> GarmentTags:
    return GarmentTags.model_validate({name: getattr(row, name) for name in GarmentTags.model_fields})


def engine_item(row: WardrobeItem) -> ClosetItem:
    return ClosetItem(id=str(row.id), **tags_of(row).model_dump())


def _columns(tags: GarmentTags) -> dict[str, Any]:
    return tags.model_dump(mode="json")


async def count(session: AsyncSession, user_id: str) -> int:
    return int(await session.scalar(select(func.count()).where(WardrobeItem.user_id == user_id)) or 0)


async def check_can_add(session: AsyncSession, user_id: str, digest: str) -> None:
    """Raise before any paid call: the closet is full, or this exact photo is already in it."""
    if await count(session, user_id) >= MAX_ITEMS_PER_USER:
        raise ClosetFullError(f"A closet holds at most {MAX_ITEMS_PER_USER} items")
    exists = await session.scalar(
        select(WardrobeItem.id).where(WardrobeItem.user_id == user_id, WardrobeItem.image_hash == digest)
    )
    if exists is not None:
        raise DuplicatePhotoError("This photo is already in your closet")


async def add(session: AsyncSession, user_id: str, tags: GarmentTags, image_bytes: bytes, digest: str) -> WardrobeItem:
    row = WardrobeItem(user_id=user_id, image=thumbnail_jpeg(image_bytes), image_hash=digest, **_columns(tags))
    session.add(row)
    await session.flush()
    return row


async def list_items(session: AsyncSession, user_id: str) -> list[WardrobeItem]:
    rows = await session.scalars(
        select(WardrobeItem).where(WardrobeItem.user_id == user_id).order_by(WardrobeItem.created_at, WardrobeItem.id)
    )
    return list(rows)


async def get(session: AsyncSession, user_id: str, item_id: uuid.UUID) -> WardrobeItem | None:
    row = await session.get(WardrobeItem, item_id)
    return row if row is not None and row.user_id == user_id else None


async def update(session: AsyncSession, row: WardrobeItem, changes: dict[str, Any]) -> WardrobeItem:
    """Apply a user's tag corrections; category and colour family follow, then all tags are re-validated."""
    if "garment_type" in changes:
        changes["category"] = category_of(changes["garment_type"])
    if changes.get("color") is not None:
        changes["color_family"] = COARSE_COLOR[ColorName(changes["color"])]
    tags = GarmentTags.model_validate({**tags_of(row).model_dump(), **changes})
    for key, value in _columns(tags).items():
        setattr(row, key, value)
    await session.flush()
    return row


async def remove(session: AsyncSession, user_id: str, item_id: uuid.UUID) -> bool:
    result = await session.execute(
        delete(WardrobeItem).where(WardrobeItem.user_id == user_id, WardrobeItem.id == item_id)
    )
    return bool(getattr(result, "rowcount", 0))


def demo_items() -> list[tuple[GarmentTags, bytes]]:
    """The prebuilt demo closet (``evaluation/build_demo_closet.py``): tags and stored JPEGs."""
    entries = json.loads((DEMO_DIR / "items.json").read_text())
    return [(GarmentTags.model_validate(e["tags"]), (DEMO_DIR / e["file"]).read_bytes()) for e in entries]


async def copy_demo(session: AsyncSession, user_id: str) -> int:
    """Copy the demo closet into *user_id*'s closet. Idempotent: items already there are skipped."""
    have = set(await session.scalars(select(WardrobeItem.image_hash).where(WardrobeItem.user_id == user_id)))
    room = MAX_ITEMS_PER_USER - len(have)
    added = 0
    for tags, jpeg in demo_items():
        digest = image_hash(jpeg)
        if digest in have or added >= room:
            continue
        session.add(WardrobeItem(user_id=user_id, image=jpeg, image_hash=digest, **_columns(tags)))
        added += 1
    await session.flush()
    return added


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def new_mcp_key(session: AsyncSession, user_id: str) -> str:
    """A fresh MCP key for this closet (192 random bits). It replaces any earlier key."""
    key = secrets.token_urlsafe(24)
    await session.merge(McpKey(user_id=user_id, key_hash=_key_hash(key)))
    return key


async def mcp_user(session: AsyncSession, key: str) -> str | None:
    """Whose closet an MCP key opens, or None."""
    user_id: str | None = await session.scalar(select(McpKey.user_id).where(McpKey.key_hash == _key_hash(key)))
    return user_id
