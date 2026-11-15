"""The wear log: one user's ``wear_events`` rows, read back as ``engine.preferences`` events."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine import preferences
from backend.models.records import WardrobeItem, WearEvent


class NotInClosetError(Exception):
    pass


async def record(
    session: AsyncSession,
    user_id: str,
    item_ids: list[uuid.UUID],
    action: preferences.Action,
    occasion: str | None,
    day: dt.date,
) -> WearEvent:
    """Save one event. Every item must be in *user_id*'s closet, so nobody can vote on another's items."""
    ids = list(dict.fromkeys(item_ids))
    owned = set(
        await session.scalars(select(WardrobeItem.id).where(WardrobeItem.user_id == user_id, WardrobeItem.id.in_(ids)))
    )
    if len(owned) != len(ids):
        raise NotInClosetError("Some items are not in this closet")
    row = WearEvent(user_id=user_id, item_ids=[str(i) for i in ids], action=action, occasion=occasion, day=day)
    session.add(row)
    await session.flush()
    return row


async def events(session: AsyncSession, user_id: str) -> list[preferences.WearEvent]:
    # shortcut: reads the whole log on every request; fine for a demo (a few events a day).
    # Keep running totals per item and pair if logs reach thousands of rows.
    rows = await session.scalars(select(WearEvent).where(WearEvent.user_id == user_id).order_by(WearEvent.day))
    return [preferences.WearEvent(tuple(r.item_ids), cast(preferences.Action, r.action), r.day) for r in rows]
