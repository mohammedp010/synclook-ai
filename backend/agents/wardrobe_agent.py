"""Wardrobe Agent — "wear what you own first".

For each recommended item, checks the user's digital closet for a matching
garment (tag-gated, embedding-ranked). Matches are marked ``owned`` with a
``wardrobe_item_id`` so the shopping stage skips them — products are only
fetched for the pieces the user is actually missing.

This agent is an enhancement: any failure (no DB, empty closet) leaves the
recommendations untouched.
"""

from __future__ import annotations

from backend.agents.base import AgentContext, BaseAgent
from backend.core.logging import get_logger
from backend.db.session import async_session_factory
from backend.schemas.api import Recommendation
from backend.services.wardrobe import WardrobeService

logger = get_logger(__name__)


class WardrobeAgent(BaseAgent):
    """Marks recommendation items the user can already wear from their closet."""

    name = "wardrobe"

    def __init__(self, wardrobe_service: WardrobeService) -> None:
        super().__init__()
        self._wardrobe = wardrobe_service

    async def _execute(self, ctx: AgentContext) -> AgentContext:
        if not ctx.user_id or not ctx.recommendations:
            return ctx

        matched = 0
        async with async_session_factory() as session:
            for rec in ctx.recommendations:
                if not isinstance(rec, Recommendation):
                    continue
                for item in rec.items:
                    if item.owned:
                        continue
                    match = await self._wardrobe.find_match(
                        session,
                        user_id=ctx.user_id,
                        item_type=item.item_type,
                        color=item.color,
                        style=item.style,
                    )
                    if match is not None:
                        item.owned = True
                        item.wardrobe_item_id = str(match.item.id)
                        item.reason = (
                            f"You already own this: {match.item.label or match.item.color} "
                            f"{match.item.clothing_type} from your wardrobe."
                        )
                        matched += 1

        ctx.metadata["wardrobe_matches"] = matched
        logger.info("wardrobe_complete", user_id=ctx.user_id, matches=matched)
        return ctx
