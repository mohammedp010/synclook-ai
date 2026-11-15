"""ORM models for persistent storage."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, LargeBinary, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class WardrobeItem(Base):
    """One garment in a user's closet: the Phase 2 tags, a small JPEG and the upload's hash.

    ``user_id`` is an opaque string the client sends (no login). ``image_hash`` is the
    SHA-256 of the uploaded bytes; one user cannot add the same photo twice.
    """

    __tablename__ = "wardrobe_items"
    __table_args__ = (UniqueConstraint("user_id", "image_hash", name="uq_wardrobe_items_user_image"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    garment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False)
    color_family: Mapped[str] = mapped_column(String(16), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)
    secondary_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pattern: Mapped[str] = mapped_column(String(32), nullable=False, default="solid")
    formality: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    warmth: Mapped[str] = mapped_column(String(8), nullable=False)
    occasions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    short_label: Mapped[str] = mapped_column(String(64), nullable=False)
    item_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # shortcut: photos live in Postgres because free hosts have no persistent disk; move to object storage
    # if items exceed a few thousand.
    image_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WearEvent(Base):
    """One outfit a user wore, saved or skipped (``engine.preferences`` counts these).

    ``item_ids`` is a JSON list of ``wardrobe_items`` ids, not foreign keys: deleting an
    item keeps the history, and the counting ignores ids no longer in the closet.
    """

    __tablename__ = "wear_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    item_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KvCacheEntry(Base):
    """One cached JSON value (``services.cache.KvCache``); stale once ``expires_at`` passes."""

    __tablename__ = "kv_cache"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class McpKey(Base):
    """The secret in one closet's MCP URL (``backend/mcp_server.py``), one per closet.

    Only the key's SHA-256 is stored, so a copy of the database holds no working URL. Asking for a
    new key overwrites the row, which turns the old URL off.
    """

    __tablename__ = "mcp_keys"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
