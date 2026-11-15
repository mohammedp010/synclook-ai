"""Chat with the closet: one user message → the agent's tool steps and reply, streamed as server-sent events."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agent import run_turn
from backend.api.routes.closet import Cache, Db, UserId
from backend.core import budget
from backend.core.config import get_settings
from backend.core.dependencies import (
    get_llm_service,
    get_product_judge,
    get_product_search_tool,
    get_weather_service,
)
from backend.core.rate_limit import limiter
from backend.services.llm import LLMService
from backend.toolkit import Ctx

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(
        default_factory=list, max_length=12, description="The last few messages; the server keeps no state"
    )


@router.post("/chat", response_class=StreamingResponse)
@limiter.limit(get_settings().paid_rate_limit)
async def chat(
    request: Request,
    body: ChatRequest,
    user_id: UserId,
    db: Db,
    cache: Cache,
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> StreamingResponse:
    """Server-sent events, one JSON object each: ``tool_call``, ``tool_result``, ``reply``, ``done``.

    One turn counts against the daily chat cap before the stream starts, so over the cap it is a plain 429.

    shortcut: the reply arrives as one event, not token by token; stream the final step if replies get long.
    """
    await budget.spend(cache, "chat_turns", get_settings().chat_daily_cap)
    ctx = Ctx(
        db=db,
        user_id=user_id,
        weather=get_weather_service(),
        products=get_product_search_tool(),
        judge=get_product_judge(),
        cache=cache,
    )
    history = [m.model_dump() for m in body.history]

    async def events() -> AsyncIterator[str]:
        async for event in run_turn(llm, ctx, history, body.message):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
