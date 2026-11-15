"""The MCP server: the same five ``toolkit.TOOLS`` for Claude, ChatGPT or any MCP client.

Served by the FastAPI app over Streamable HTTP at ``{api_prefix}/mcp/{key}/``. ``POST /closet/mcp-key``
gives a closet its key; the key decides whose closet every call reads and writes. Each call runs through
``toolkit.run_tool``, the same path as the in-app chat agent, so there is no second copy of any logic.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.core.config import get_settings
from backend.core.dependencies import get_cache, get_product_judge, get_product_search_tool, get_weather_service
from backend.core.rate_limit import mcp_allowed
from backend.db.session import async_session_factory
from backend.services import closet
from backend.toolkit import TOOLS, Ctx, run_tool

INSTRUCTIONS = (
    "Synclook holds one person's real closet and the style rules for it. Use the tools instead of guessing. "
    "Outfits come only from build_outfits: never assemble or edit one yourself; to swap a piece, call it again with "
    "that piece's id in exclude_item_ids. Name only items and products a tool returned, and write each item's id "
    "next to its label so the user can say which outfit they mean. log_wear writes to the wear log and "
    "search_products costs money; the other three tools are free and read-only."
)

_SIDE_EFFECT = " One of only two tools here with a side effect or a cost (log_wear and search_products)."

# What each tool returns, for a client model that sees only these descriptions. Kept here, not in
# ``toolkit``, so the in-app agent's tool schemas (and its cached eval replies) stay unchanged.
_RETURNS = {
    "list_closet": "Returns {count, items: [{id, label, type, category, color, formality, warmth}]}.",
    "build_outfits": "Returns {occasion, weather, outfits: [{items: [{id, label, type}], score, evidence}], "
    "reason, notes}; 'reason' explains an empty list.",
    "find_gap_item": "Returns {gaps: [{garment_type, color, label, new_outfits, occasions_unlocked, example}]}, "
    "best first; pass garment_type and color to search_products to shop for one.",
    "search_products": "Returns {query, checked, products: [{title, price, source, link}], note, "
    "searches_left_today}." + _SIDE_EFFECT,
    "log_wear": "Returns {logged: {id, items, action, date}}, or needs_choice with the outfits to ask about."
    + _SIDE_EFFECT,
}

_LISTED = [
    Tool(
        name=t.name,
        description=f"{t.description} {_RETURNS[t.name]}",
        input_schema=t.args.model_json_schema(),
        annotations=ToolAnnotations(
            read_only_hint=t.name != "log_wear",
            destructive_hint=False,
            open_world_hint=t.name == "search_products",
        ),
    )
    for t in TOOLS
]
_BY_NAME = {t.name: t for t in TOOLS}
_USER = "synclook.user_id"  # set on the ASGI scope by the key check in ``asgi_app``


async def _list_tools(_ctx: ServerRequestContext[Any, Any], _params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=_LISTED)


async def _call_tool(ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams) -> CallToolResult:
    assert ctx.request is not None  # served only over HTTP, behind the key check
    async with async_session_factory() as db:
        tool_ctx = Ctx(
            db=db,
            user_id=ctx.request.scope[_USER],
            weather=get_weather_service(),
            products=get_product_search_tool(),
            judge=get_product_judge(),
            cache=get_cache(),
        )
        result = await run_tool(_BY_NAME, tool_ctx, params.name, json.dumps(params.arguments or {}))
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, default=str))], is_error="error" in result
    )


server: Server[Any] = Server(
    "synclook",
    version=get_settings().app_version,
    instructions=INSTRUCTIONS,
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)


def asgi_app() -> tuple[ASGIApp, StreamableHTTPSessionManager]:
    """A new MCP endpoint behind the key check, and its session manager, which the host app's lifespan must run.

    One pair per FastAPI app: a session manager can be run only once.
    """
    mcp_http = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,  # no session kept between requests: nothing to lose on a restart or a second worker
        json_response=True,
        # The default allowlist accepts only a localhost Host header, which refuses every tunnel or deployed
        # hostname. The unguessable key in the path is what stops a stray web page from reaching a closet.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Over the visitor's rate limit is a 429 and an unknown key a 404, both before any MCP code runs."""
        if not mcp_allowed((scope.get("client") or ("unknown",))[0]):
            await JSONResponse({"detail": "Too many requests; try again in a minute"}, status_code=429)(
                scope, receive, send
            )
            return
        # shortcut: URL key instead of OAuth; fine for a demo, upgrade before real users.
        async with async_session_factory() as db:
            user_id = await closet.mcp_user(db, scope["path_params"]["key"])
        if user_id is None:
            await JSONResponse({"detail": "Unknown MCP key"}, status_code=404)(scope, receive, send)
            return
        await mcp_http({**scope, _USER: user_id}, receive, send)

    return app, server.session_manager
