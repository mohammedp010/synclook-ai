"""What one thing should I buy? Gap items from the closet (free), then checked products for one (paid)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.api.routes.closet import Cache, Db, UserId, image_url
from backend.core import budget
from backend.core.config import get_settings
from backend.core.dependencies import get_product_judge, get_product_search_tool
from backend.core.logging import get_logger
from backend.core.rate_limit import limiter
from backend.engine.gaps import CANDIDATE_ID, MAX_GAPS, candidates, find_gaps
from backend.schemas.api import (
    GapOut,
    GapPiece,
    GapsRequest,
    GapsResponse,
    ShopSearchRequest,
    ShopSearchResponse,
)
from backend.schemas.clothing import Color
from backend.schemas.taxonomy import GarmentType
from backend.services import closet
from backend.services.product_judge import ProductJudge
from backend.toolkit import checked_products
from backend.tools.product_search import ProductSearchTool

logger = get_logger(__name__)

router = APIRouter(prefix="/shop")


@router.post("/gaps")
async def gaps(user_id: UserId, db: Db, request: GapsRequest | None = None) -> GapsResponse:
    """The 3 purchases that add the most new outfits, each with an example. Rules only: no paid call."""
    buyer = request.buyer if request else "all"
    items = [closet.engine_item(r) for r in await closet.list_items(db, user_id)]
    if not items:
        return GapsResponse(
            gaps=[],
            candidates_checked=0,
            reason="Your closet is empty: add items, or POST /closet/demo to try the demo closet.",
        )
    found = find_gaps(items, buyer)
    out = [
        GapOut(
            garment_type=GarmentType(g.garment_type),
            color=Color(g.color_family),
            label=g.label,
            new_outfits=g.new_outfits,
            new_outfits_by_occasion=g.per_occasion,
            occasions_unlocked=g.unlocked,
            example_occasion=g.example_occasion,
            example=[
                GapPiece(
                    id=None if i.id == CANDIDATE_ID else uuid.UUID(i.id),
                    short_label=i.short_label,
                    garment_type=i.garment_type,
                    category=i.category,
                    image_url=None if i.id == CANDIDATE_ID else image_url(i.id),
                )
                for i in g.example.items
            ],
            example_evidence=list(g.example.evidence),
        )
        for g in found
    ]
    reason = None
    if len(out) < MAX_GAPS:
        reason = f"Only {len(out)} of the common items we check would add an outfit to this closet."
    return GapsResponse(gaps=out, candidates_checked=len(candidates(items, buyer)), reason=reason)


@router.post("/search")
@limiter.limit(get_settings().search_rate_limit)
async def search(
    request: Request,
    body: ShopSearchRequest,
    user_id: UserId,
    cache: Cache,
    tool: Annotated[ProductSearchTool, Depends(get_product_search_tool)],
    judge: Annotated[ProductJudge, Depends(get_product_judge)],
) -> ShopSearchResponse:
    """Products for one item: one SerpAPI search (cached 7 days), one Jev call. Only checked products are shown.

    Counts against the same daily search cap as the chat agent's and MCP's ``search_products``.
    """
    await budget.spend(cache, "product_searches", get_settings().search_daily_cap)
    return await checked_products(tool, judge, body)
