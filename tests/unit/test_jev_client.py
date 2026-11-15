"""Tests for the Jev client — wire format, parsing, and the failure policy.

No network: every test drives ``httpx.MockTransport``. The failure policy is the
part worth pinning, because each branch maps to a different caller behaviour —
a 422 is our bug and must surface, a 529 is weather and must be retried, a
timeout must end the wait at once so perception can fall back to CLIP.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from backend.core.config import Settings
from backend.services import jev
from backend.services.jev import (
    Choice,
    ChoiceAnswer,
    JevClient,
    JevError,
    JevRequestError,
    JevUnavailableError,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
)

PINNED = "jev-1.13.0"


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "jev_api_key": "test-key",
        "jev_base_url": "https://api.typesafe.ai",
        "jev_model": PINNED,
        "jev_max_retries": 2,
    }
    base.update(overrides)
    return Settings(**base)


def _ok_body(answers: dict[str, Any], model: str = PINNED) -> dict[str, Any]:
    return {"model": model, "answers": answers, "usage": {"input_tokens": 321, "output_tokens": 0}}


def _client(handler: Callable[[httpx.Request], httpx.Response], **overrides: Any) -> JevClient:
    return JevClient(settings=_settings(**overrides), transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(jev.asyncio, "sleep", fake_sleep)
    return slept


QUESTIONS: dict[str, jev.Question] = {
    "beach": Noul("Would a well-dressed person wear this to a beach day?", true="Yes, fits", false="No"),
    "category": Choice("What kind of garment is this?", {"topwear": None, "bottomwear": None, "other": None}),
    "formality": Score("How formal is this garment?", ("Loungewear", "Casual", "Business", "Black tie")),
}

ANSWERS = {
    "beach": {"type": "noul", "noul": 0.83},
    "category": {
        "type": "choice",
        "choice": "topwear",
        "probabilities": {"topwear": 0.9, "bottomwear": 0.05, "other": 0.05},
        "confidence": 0.81,
    },
    "formality": {
        "type": "score",
        "score": 1.2,
        "legend": {"0": "Loungewear", "1": "Casual", "2": "Business", "3": "Black tie"},
        "probabilities": {"0": 0.0, "1": 0.8, "2": 0.2, "3": 0.0},
        "confidence": 0.7,
    },
}


# ── Wire format ──────────────────────────────────────────────────────


async def test_request_carries_pinned_model_auth_and_typed_questions() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_body(ANSWERS))

    await _client(handler).judge({"garment": "navy wool blazer"}, QUESTIONS)

    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["model"] == PINNED
    assert body["state"] == {"garment": "navy wool blazer"}
    assert body["questions"]["beach"] == {
        "type": "noul",
        "instructions": "Would a well-dressed person wear this to a beach day?",
        "criteria": {"true": "Yes, fits", "false": "No"},
    }
    assert body["questions"]["category"]["criteria"] == {"topwear": None, "bottomwear": None, "other": None}
    assert body["questions"]["formality"]["criteria"] == ["Loungewear", "Casual", "Business", "Black tie"]


async def test_noul_without_criteria_omits_the_field() -> None:
    assert "criteria" not in Noul("Is this a garment?").to_json()


# ── Parsing ──────────────────────────────────────────────────────────


async def test_answers_parse_into_typed_objects() -> None:
    resp = await _client(lambda _: httpx.Response(200, json=_ok_body(ANSWERS))).judge("state", QUESTIONS)

    assert resp.noul("beach") == NoulAnswer(p=0.83)
    assert isinstance(resp.choice("category"), ChoiceAnswer)
    assert resp.choice("category").choice == "topwear"
    formality = resp.score("formality")
    assert isinstance(formality, ScoreAnswer)
    assert formality.probabilities == {0: 0.0, 1: 0.8, 2: 0.2, 3: 0.0}
    assert formality.legend[3] == "Black tie"
    assert resp.input_tokens == 321
    assert resp.model == PINNED


async def test_asking_for_the_wrong_answer_type_raises() -> None:
    resp = await _client(lambda _: httpx.Response(200, json=_ok_body(ANSWERS))).judge("state", QUESTIONS)
    with pytest.raises(JevError):
        resp.choice("beach")


async def test_missing_answer_is_an_error_not_a_silent_gap() -> None:
    partial = {k: v for k, v in ANSWERS.items() if k != "formality"}
    with pytest.raises(JevError, match="formality"):
        await _client(lambda _: httpx.Response(200, json=_ok_body(partial))).judge("state", QUESTIONS)


async def test_malformed_answer_raises() -> None:
    broken = dict(ANSWERS, beach={"type": "noul"})
    with pytest.raises(JevError, match="beach"):
        await _client(lambda _: httpx.Response(200, json=_ok_body(broken))).judge("state", QUESTIONS)


async def test_model_mismatch_still_answers() -> None:
    # An alias moved under us. The answer is usable; the warning is the point.
    body = _ok_body(ANSWERS, model="jev-1.14.0")
    resp = await _client(lambda _: httpx.Response(200, json=body)).judge("state", QUESTIONS)
    assert resp.model == "jev-1.14.0"


# ── Local validation — fail before spending a request ─────────────────


def test_score_rejects_bare_numeric_levels() -> None:
    with pytest.raises(JevRequestError, match="situations"):
        Score("How severe?", ("0", "1", "2"))


@pytest.mark.parametrize("levels", [("only one",), tuple(f"level {i}" for i in range(11))])
def test_score_level_count_is_bounded(levels: tuple[str, ...]) -> None:
    with pytest.raises(JevRequestError):
        Score("How formal?", levels)


def test_choice_option_count_is_bounded() -> None:
    with pytest.raises(JevRequestError):
        Choice("Which?", {"only": None})
    with pytest.raises(JevRequestError):
        Choice("Which?", {f"o{i}": None for i in range(256)})


async def test_disabled_client_raises_unavailable_without_a_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made without a key")

    client = _client(handler, jev_api_key="")
    assert not client.enabled
    with pytest.raises(JevUnavailableError):
        await client.judge("state", QUESTIONS)


# ── Failure policy ───────────────────────────────────────────────────


@pytest.mark.parametrize("status", [401, 422])
async def test_client_errors_are_not_retried(status: int) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"detail": "questions.formality.criteria: too few levels"})

    with pytest.raises(JevRequestError) as info:
        await _client(handler).judge("state", QUESTIONS)
    assert calls == 1
    if status == 422:
        assert "formality" in (info.value.detail or "")


@pytest.mark.parametrize("status", [429, 529, 503])
async def test_transient_errors_retry_then_succeed(status: int, _no_sleep: list[float]) -> None:
    responses = [httpx.Response(status), httpx.Response(200, json=_ok_body(ANSWERS))]
    resp = await _client(lambda _: responses.pop(0)).judge("state", QUESTIONS)
    assert resp.noul("beach").p == 0.83
    assert _no_sleep == [0.2]


async def test_retries_are_exhausted_into_unavailable(_no_sleep: list[float]) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(529)

    with pytest.raises(JevUnavailableError):
        await _client(handler).judge("state", QUESTIONS)
    assert calls == 3  # one try + jev_max_retries
    assert _no_sleep == [0.2, 0.4]  # exponential


async def test_retry_after_is_honoured(_no_sleep: list[float]) -> None:
    responses = [httpx.Response(429, headers={"retry-after": "1.5"}), httpx.Response(200, json=_ok_body(ANSWERS))]
    await _client(lambda _: responses.pop(0)).judge("state", QUESTIONS)
    assert _no_sleep == [1.5]


async def test_long_retry_after_gives_up_rather_than_stalling_a_user(_no_sleep: list[float]) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"retry-after": "30"})

    with pytest.raises(JevUnavailableError):
        await _client(handler).judge("state", QUESTIONS)
    assert calls == 1
    assert _no_sleep == []


async def test_timeout_is_unavailable_immediately() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(JevUnavailableError, match="timed out"):
        await _client(handler).judge("state", QUESTIONS)
    assert calls == 1


async def test_connection_errors_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json=_ok_body(ANSWERS))

    await _client(handler).judge("state", QUESTIONS)
    assert calls == 2
