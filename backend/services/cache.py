"""Key-value cache with a TTL, stored in Postgres (the ``kv_cache`` table).

It replaces Redis: product searches, perception results and other small
answers worth keeping for hours or days. One less service to host.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.session import async_session_factory
from backend.models.records import KvCacheEntry


class KvCache:
    """``get`` returns the stored JSON value, or None when missing or expired."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = async_session_factory) -> None:
        self._sessions = session_factory

    async def get(self, key: str) -> Any | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(KvCacheEntry.value).where(KvCacheEntry.key == key, KvCacheEntry.expires_at > datetime.now(UTC))
            )
        return row

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # shortcut: expired rows stay until their key is written again; add a purge if the table grows large.
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        stmt = insert(KvCacheEntry).values(key=key, value=value, expires_at=expires_at)
        stmt = stmt.on_conflict_do_update(
            index_elements=[KvCacheEntry.key], set_={"value": value, "expires_at": expires_at}
        )
        async with self._sessions() as session:
            await session.execute(stmt)
            await session.commit()
