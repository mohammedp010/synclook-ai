"""The wear log: record what was worn, saved or skipped. ``POST /outfits`` learns from it."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, status

from backend import toolkit
from backend.api.routes.closet import Db, UserId
from backend.schemas.api import WearOut, WearRequest
from backend.services import wear

router = APIRouter()


@router.post("/wear", status_code=status.HTTP_201_CREATED)
async def record_wear(request: WearRequest, user_id: UserId, db: Db) -> WearOut:
    try:
        return await toolkit.record_wear(db, user_id, request, dt.date.today())
    except toolkit.FutureDateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except wear.NotInClosetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
