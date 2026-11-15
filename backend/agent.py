"""The chat agent: a hand-written tool-calling loop on the text model (no framework, decision D2).

One user turn = at most ``MAX_STEPS`` model calls and ``MAX_TOKENS_PER_TURN`` tokens. Each step the
model either calls tools from ``toolkit.TOOLS`` or answers. The model picks tools; the rules in
``engine/`` still decide what a valid outfit is, so it cannot invent items or break a rule. A bad
tool name, bad arguments or a failing tool go back to the model as an error result, never a crash.
No nested agents: a tool is a plain function.

``run_turn`` yields events (dicts) so ``POST /chat`` can stream them:
``tool_call``, ``tool_result``, ``reply`` (always exactly one) and ``done`` (steps, tokens, stop reason).

A reply may only name item ids (``[id]``) that a tool returned this turn or the history showed;
otherwise it is sent back once for a correction, then replaced by a fixed message. When
``build_outfits`` says a requested item is ``missing`` from the closet and the reply does not say
so, a fixed sentence saying so goes in front of it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from typing import Any, Literal, cast

from openai.types.chat import ChatCompletionMessageFunctionToolCall

from backend.core.exceptions import LLMError
from backend.core.logging import get_logger
from backend.engine.requests import says_missing
from backend.schemas.taxonomy import OCCASION_DESCRIPTIONS
from backend.services.llm import LLMService
from backend.toolkit import TOOLS, Ctx, Tool, run_tool

logger = get_logger(__name__)

MAX_STEPS = 6
# A normal turn measured ~4–8k tokens (system prompt + 5 tool schemas ≈ 2k, a closet list ≈ 2k).
MAX_TOKENS_PER_TURN = 20_000
MAX_REPLY_TOKENS = 600

Stop = Literal["step_limit", "token_limit", "model_error", "invented_items"]

_FALLBACK: dict[Stop, str] = {
    "step_limit": "Sorry, I could not finish that in a few steps. Could you ask in a simpler way?",
    "token_limit": "Sorry, that conversation got too long for one answer. Could you ask again more briefly?",
    "model_error": "Sorry, the assistant is unavailable right now. Please try again in a moment.",
    "invented_items": "Sorry, I could not build that from your closet. Try asking for an outfit for an occasion.",
}

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_BRACKETED = re.compile(r"\[([0-9a-fA-F][0-9a-fA-F.-]{6,})\]")  # also catches a shortened "[3f2a...]"

_NUDGE = "(Please answer my last message now, using the tool results above.)"
_CORRECTION = (
    "(Your reply named item ids that no tool returned, so those items do not exist. Answer again using only "
    "items from tool results; for a new outfit, call build_outfits.)"
)


def system_prompt(today: dt.date) -> str:
    occasions = "\n".join(f"- {o.value}: {d}" for o, d in OCCASION_DESCRIPTIONS.items())
    return (
        f"You are Synclook's closet assistant. Today is {today:%A %Y-%m-%d}; "
        f"yesterday was {today - dt.timedelta(days=1)}. You help one user with their own closet, only through "
        "the tools.\n"
        "Rules:\n"
        "- Name only items, outfits and products that a tool returned in this conversation. Never invent any.\n"
        "- Outfits come only from build_outfits. Never assemble or edit an outfit yourself: to swap a piece, call "
        "build_outfits again with that piece's id in exclude_item_ids; for warmer or cooler, set temperature_c.\n"
        "- When the user says they wore, liked/saved or skipped an outfit, call log_wear once with that outfit's "
        "item ids. If several outfits were shown and it is unclear which one, ask which before logging.\n"
        "- For 'what should I buy', call find_gap_item. Call search_products only when the user wants to see "
        "products (it costs money); for 'cheaper', search again with a lower max_price.\n"
        "- When you show an outfit, write each piece as its label then its id in square brackets, e.g. "
        "'white tee [3f2a...]', with the full id, so later messages can refer to it.\n"
        "- If build_outfits lists items as missing, first tell the user the closet does not have them, then offer "
        "the outfits as the closest alternatives.\n"
        "- If a tool returns an error or a reason, tell the user plainly. Ask a short question if the request is "
        "unclear. Reply in under 120 words, no tables.\n"
        f"Occasions:\n{occasions}"
    )


async def run_turn(
    llm: LLMService,
    ctx: Ctx,
    history: Sequence[dict[str, str]],
    message: str,
    *,
    tools: Sequence[Tool] = TOOLS,
    max_steps: int = MAX_STEPS,
    max_tokens: int = MAX_TOKENS_PER_TURN,
) -> AsyncIterator[dict[str, Any]]:
    """Answer one user message. *history* is the client's short ``{role, content}`` list (stateless)."""
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    with_items = [m["content"] for m in history if m["role"] == "assistant" and _UUID.search(m["content"])]
    ctx = replace(ctx, message=message, shown=with_items[-1] if with_items else "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx.today)},
        *({"role": m["role"], "content": m["content"]} for m in history),
        {"role": "user", "content": message},
    ]
    used, steps, empty, corrections = 0, 0, 0, 0
    stop: Stop | None = None
    reply: str | None = None
    # Ids the model may name: those a tool returned this turn or the history already showed.
    known = set(_UUID.findall(" ".join(m["content"] for m in history)))
    missing: dict[str, None] = {}  # requested items the closet lacks, in order

    while reply is None and stop is None:
        if steps >= max_steps:
            stop = "step_limit"
            break
        if used >= max_tokens:
            stop = "token_limit"
            break
        steps += 1
        try:
            response = await llm.complete_with_tools(
                messages, schemas, max_tokens=min(MAX_REPLY_TOKENS, max_tokens - used)
            )
        except LLMError as exc:
            logger.warning("agent_model_error", error=str(exc))
            stop = "model_error"
            break
        used += response.usage.total_tokens if response.usage else 0
        msg = response.choices[0].message if response.choices else None
        # Only function calls are offered; a custom-tool call would be a provider bug and is ignored.
        calls = cast(
            list[ChatCompletionMessageFunctionToolCall],
            [c for c in ((msg.tool_calls or []) if msg else []) if c.type == "function"],
        )
        if msg is None or not calls:
            if msg and msg.content and msg.content.strip():
                text = msg.content.strip()
                unknown = sorted({i for i in _BRACKETED.findall(text) if i not in known})
                if not unknown:
                    reply = text
                elif corrections == 0:
                    # Both eval models once wrote a whole outfit of made-up items after a skip. The rules,
                    # not the model, make outfits: send it back once, then refuse (as the explainer does).
                    corrections += 1
                    messages += [{"role": "assistant", "content": text}, {"role": "user", "content": _CORRECTION}]
                else:
                    stop = "invented_items"
            else:
                # Gemini Flash-Lite ended 6 of 21 eval turns with neither text nor a call right after a
                # tool result, and the identical request fails again at temperature 0. A nudge changes it.
                empty += 1
                messages.append({"role": "user", "content": _NUDGE})
            continue
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments},
                    }
                    for c in calls
                ],
            }
        )
        for call in calls:
            name = call.function.name
            yield {"type": "tool_call", "name": name, "arguments": call.function.arguments}
            result = await run_tool(by_name, ctx, name, call.function.arguments)
            yield {"type": "tool_result", "name": name, "result": result}
            content = json.dumps(result, default=str)
            known |= set(_UUID.findall(content))
            missing |= dict.fromkeys(result.get("missing") or []) if name == "build_outfits" else {}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

    if reply is not None and (unsaid := [m for m in missing if not says_missing(m, reply)]):
        # The model offered "swimwear outfits" from a tee and shorts (Phase 8, 3 of 4 such requests): the
        # code, not the prompt, makes sure the user hears the closet cannot do it.
        reply = f"Your closet has no {' or '.join(unsaid)}, so these are the closest alternatives you own.\n\n{reply}"
    yield {"type": "reply", "text": reply if reply is not None else _FALLBACK[stop or "step_limit"]}
    yield {
        "type": "done",
        "steps": steps,
        "tokens": used,
        "stopped": stop,
        "empty_steps": empty,
        "corrections": corrections,
    }
