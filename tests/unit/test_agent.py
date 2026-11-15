"""The chat loop with a scripted model: limits hold, and every kind of tool failure goes back to the model."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from pydantic import BaseModel

from backend.agent import _NUDGE, MAX_REPLY_TOKENS, run_turn
from backend.core.exceptions import LLMError, ToolError
from backend.toolkit import Ctx, Tool


def reply(content: str | None = None, calls: Iterable[tuple[str, str]] = (), tokens: int = 100) -> Any:
    tool_calls = [
        SimpleNamespace(id=f"call{n}", type="function", function=SimpleNamespace(name=name, arguments=args))
        for n, (name, args) in enumerate(calls)
    ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(total_tokens=tokens))


class FakeLLM:
    def __init__(self, *replies: Any, forever: Any = None) -> None:
        self.replies = list(replies)
        self.forever = forever
        self.complete_with_tools = AsyncMock(side_effect=self._next)

    async def _next(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, max_tokens: int) -> Any:
        if self.replies:
            item = self.replies.pop(0)
        else:
            item = self.forever
        if isinstance(item, Exception):
            raise item
        return item


class EchoArgs(BaseModel):
    word: str


async def echo(_ctx: Ctx, args: EchoArgs) -> dict[str, Any]:
    if args.word == "boom":
        raise ToolError("the echo broke")
    if args.word == "bug":
        raise KeyError("oops")
    return {"echo": args.word}


TOOLS = (Tool("echo", "Repeat a word.", EchoArgs, echo),)


def ctx() -> Ctx:
    return Ctx(
        db=AsyncMock(), user_id="u", weather=AsyncMock(), products=AsyncMock(), judge=AsyncMock(), cache=AsyncMock(),
        today=dt.date(2026, 11, 15),
    )  # fmt: skip


async def run(llm: FakeLLM, c: Ctx | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    return [e async for e in run_turn(llm, c or ctx(), [], "hi", tools=TOOLS, **kwargs)]  # type: ignore[arg-type]


def done(events: list[dict[str, Any]]) -> dict[str, Any]:
    assert [e["type"] for e in events].count("reply") == 1
    assert events[-1]["type"] == "done"
    return events[-1]


async def test_a_direct_answer_is_one_step() -> None:
    events = await run(FakeLLM(reply("Hello!")))
    assert events[0] == {"type": "reply", "text": "Hello!"}
    assert done(events) == {
        "type": "done",
        "steps": 1,
        "tokens": 100,
        "stopped": None,
        "empty_steps": 0,
        "corrections": 0,
    }


async def test_a_tool_result_goes_back_with_its_call_id() -> None:
    llm = FakeLLM(reply(calls=[("echo", '{"word": "hey"}')]), reply("It said hey."))
    events = await run(llm)
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "reply", "done"]
    assert events[1]["result"] == {"echo": "hey"}
    second_call_messages = llm.complete_with_tools.await_args_list[1].args[0]
    assistant, tool = second_call_messages[-2:]
    assert assistant["tool_calls"][0]["id"] == "call0" and tool["tool_call_id"] == "call0"
    assert json.loads(tool["content"]) == {"echo": "hey"}
    assert done(events)["steps"] == 2


async def test_the_step_limit_stops_a_model_that_never_answers() -> None:
    llm = FakeLLM(forever=reply(calls=[("echo", '{"word": "again"}')]))
    events = await run(llm)
    assert llm.complete_with_tools.await_count == 6
    end = done(events)
    assert end["steps"] == 6 and end["stopped"] == "step_limit"
    assert "could not finish" in events[-2]["text"]


async def test_the_token_limit_stops_the_turn_and_caps_the_last_reply() -> None:
    llm = FakeLLM(forever=reply(calls=[("echo", '{"word": "long"}')], tokens=9_000))
    events = await run(llm, max_tokens=20_000)
    assert llm.complete_with_tools.await_count == 3  # 0 → 9k → 18k → 27k: no call starts at or over 20k
    assert [c.kwargs["max_tokens"] for c in llm.complete_with_tools.await_args_list] == [MAX_REPLY_TOKENS] * 2 + [
        min(MAX_REPLY_TOKENS, 2_000)
    ]
    assert done(events)["stopped"] == "token_limit"


async def test_an_unknown_tool_is_an_error_result_and_the_loop_goes_on() -> None:
    events = await run(FakeLLM(reply(calls=[("make_outfit", "{}")]), reply("Sorry.")))
    assert "Unknown tool 'make_outfit'" in events[1]["result"]["error"]
    assert events[2] == {"type": "reply", "text": "Sorry."}


async def test_bad_arguments_are_an_error_result() -> None:
    llm = FakeLLM(reply(calls=[("echo", '{"wrd": 1}'), ("echo", "not json")]), reply("Fixed."))
    events = await run(llm)
    errors = [e["result"]["error"] for e in events if e["type"] == "tool_result"]
    assert len(errors) == 2 and all(e.startswith("Bad arguments for echo") for e in errors)
    assert "word" in errors[0]


async def test_a_failing_tool_is_an_error_result_and_the_session_is_rolled_back() -> None:
    c = ctx()
    llm = FakeLLM(reply(calls=[("echo", '{"word": "boom"}'), ("echo", '{"word": "bug"}')]), reply("Done."))
    events = await run(llm, c)
    results = [e["result"] for e in events if e["type"] == "tool_result"]
    assert results == [{"error": "the echo broke"}, {"error": "echo failed: KeyError"}]
    assert c.db.rollback.await_count == 2  # type: ignore[attr-defined]


async def test_an_empty_step_is_retried_with_a_nudge_within_the_step_budget() -> None:
    llm = FakeLLM(reply(None), reply("  "), reply("Here."))
    events = await run(llm)
    end = done(events)
    assert end["steps"] == 3 and end["empty_steps"] == 2 and events[0]["text"] == "Here."
    last_request = llm.complete_with_tools.await_args.args[0]
    assert [m["content"] for m in last_request[-2:]] == [_NUDGE, _NUDGE]  # the retry is never the same request


async def test_a_model_error_ends_the_turn_with_a_plain_message() -> None:
    events = await run(FakeLLM(LLMError("down")))
    assert done(events)["stopped"] == "model_error" and "unavailable" in events[0]["text"]


async def test_history_is_passed_through_and_the_system_prompt_has_the_date() -> None:
    llm = FakeLLM(reply("ok"))
    history = [{"role": "user", "content": "outfit?"}, {"role": "assistant", "content": "white tee [abc]"}]
    _ = [e async for e in run_turn(llm, ctx(), history, "swap it", tools=TOOLS)]  # type: ignore[arg-type]
    messages = llm.complete_with_tools.await_args.args[0]
    assert "2026-11-15" in messages[0]["content"] and "2026-11-14" in messages[0]["content"]
    assert messages[1:] == [*history, {"role": "user", "content": "swap it"}]


OWNED = "11111111-2222-4333-8444-555555555555"
MADE_UP = "99999999-8888-4777-8666-555555555555"


async def test_a_reply_naming_an_unseen_id_is_sent_back_once_for_a_correction() -> None:
    llm = FakeLLM(
        reply(calls=[("echo", json.dumps({"word": OWNED}))]),
        reply(f"Wear the silver earrings [{MADE_UP}]."),
        reply(f"Wear the tee [{OWNED}]."),
    )
    events = await run(llm)
    assert events[-2] == {"type": "reply", "text": f"Wear the tee [{OWNED}]."}
    assert done(events)["corrections"] == 1
    assert "do not exist" in llm.complete_with_tools.await_args.args[0][-1]["content"]


async def test_a_second_invented_reply_is_replaced_by_a_fixed_message() -> None:
    events = await run(FakeLLM(forever=reply(f"Try the white blouse [{MADE_UP}] or [3f2a...].")))
    end = done(events)
    assert end["stopped"] == "invented_items" and end["steps"] == 2
    assert MADE_UP not in events[-2]["text"] and "closet" in events[-2]["text"]


async def test_ids_from_the_history_may_be_named_again() -> None:
    history = [{"role": "assistant", "content": f"Outfit 1: tee [{OWNED}]."}]
    llm = FakeLLM(reply(f"Logged the tee [{OWNED}]."))
    events = [e async for e in run_turn(llm, ctx(), history, "thanks", tools=TOOLS)]  # type: ignore[arg-type]
    assert events[-1]["stopped"] is None and OWNED in events[-2]["text"]
