"""Jev client — typed, calibrated judgments for the perception cascade (Phase 2).

Jev (TypeSafe's "System One" model) takes a text ``state`` plus a batch of typed
questions and returns typed answers with calibrated probabilities. It never
generates text. Reference: ``JEV_REFERENCE.md``; governing rule from its §1 —
*questions describe judgments; code owns composition, thresholds and side
effects.* So this module only asks and parses. No threshold lives here.

Why raw ``httpx`` and not ``typesafe-sdk``: the SDK installs from a separate
package index (``pypi.typesafe.ai``), which is a supply-chain surface to add for
what is one documented POST. The REST contract is small enough to own, and
owning it puts the retry and timeout policy where this repo can test it.

Failure policy, per reference §3.5 and plan §Phase 2:

- **401 / 422** are bugs in *our* request — raise ``JevRequestError``, never retry.
- **429 / 529 / 5xx / connection errors** — retry with exponential backoff,
  honouring ``retry-after``; exhausted retries raise ``JevUnavailableError``.
- **Timeouts** raise ``JevUnavailableError`` at once. Jev answers in ~100 ms; a 3 s
  timeout means something is wrong, and retrying would stack seconds onto a
  user's request.

Whether ``JevUnavailableError`` fails *open* or *closed* (the upload guardrail
refuses) is the caller's decision, not this
client's — the same outage means different things at different call sites.

Every response's ``model`` field is logged and compared to the pinned id: a
silent alias move would silently recalibrate every threshold (reference §9.1).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.core.config import Settings, get_settings
from backend.core.exceptions import SynclookError
from backend.core.logging import get_logger

logger = get_logger(__name__)

_ENDPOINT = "/v1/systemone"
_RETRYABLE = frozenset({429, 500, 502, 503, 504, 529})
_BACKOFF_BASE_S = 0.2
_RETRY_AFTER_CAP_S = 2.0
"""A ``retry-after`` longer than this is treated as "unavailable now" — the
caller is serving a user, and falling back beats waiting."""

MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


class JevError(SynclookError):
    """Base for Jev failures."""


class JevRequestError(JevError):
    """Our request was wrong (401, 422, or a question that fails local validation). Do not retry."""


class JevUnavailableError(JevError):
    """Jev could not answer in time — timeout, overload, or exhausted retries. Caller picks open or closed."""


# ──────────────────────────────────────────────────────────────────────
#  Questions
# ──────────────────────────────────────────────────────────────────────

Criteria = str | dict[str, Any] | list[Any]


@dataclass(frozen=True)
class Noul:
    """Yes/no as a probability. Phrase it so that high means yes (reference §3.3)."""

    instructions: Criteria
    true: str | None = None
    false: str | None = None

    def to_json(self) -> dict[str, Any]:
        body: dict[str, Any] = {"type": "noul", "instructions": self.instructions}
        if self.true is not None or self.false is not None:
            body["criteria"] = {"true": self.true, "false": self.false}
        return body


@dataclass(frozen=True)
class Choice:
    """Exactly one of up to 255 mutually exclusive options. Include an ``other`` escape."""

    instructions: Criteria
    options: dict[str, Criteria | None]

    def __post_init__(self) -> None:
        if not 2 <= len(self.options) <= MAX_CHOICE_OPTIONS:
            raise JevRequestError(f"choice needs 2-{MAX_CHOICE_OPTIONS} options, got {len(self.options)}")

    def to_json(self) -> dict[str, Any]:
        return {"type": "choice", "instructions": self.instructions, "criteria": self.options}


@dataclass(frozen=True)
class Score:
    """Position on an ordered rubric, low → high. Describe situations, never bare numbers (§3.3)."""

    instructions: Criteria
    levels: tuple[Criteria, ...]

    def __post_init__(self) -> None:
        if not MIN_SCORE_LEVELS <= len(self.levels) <= MAX_SCORE_LEVELS:
            raise JevRequestError(f"score needs {MIN_SCORE_LEVELS}-{MAX_SCORE_LEVELS} levels, got {len(self.levels)}")
        if all(isinstance(level, str) and level.strip().isdigit() for level in self.levels):
            # Documented failure mode: ["0","1","2"] scored 0.55 @ confidence 0.33
            # where described levels scored 0.0 @ 1.0 on the same input.
            raise JevRequestError("score levels must describe situations, not bare numbers")

    def to_json(self) -> dict[str, Any]:
        return {"type": "score", "instructions": self.instructions, "criteria": list(self.levels)}


Question = Noul | Choice | Score


# ──────────────────────────────────────────────────────────────────────
#  Answers
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NoulAnswer:
    p: float
    """Probability of yes. No confidence field by design: with two outcomes, this is the whole distribution."""


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    """Probability-weighted mean level. Rank or round it; do not do arithmetic on it (§3.3)."""
    probabilities: dict[int, float]
    confidence: float
    legend: dict[int, str] = field(default_factory=dict)


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class JevResponse:
    model: str
    answers: dict[str, Answer]
    input_tokens: int
    latency_ms: float

    def noul(self, key: str) -> NoulAnswer:
        return _typed(self.answers, key, NoulAnswer)

    def choice(self, key: str) -> ChoiceAnswer:
        return _typed(self.answers, key, ChoiceAnswer)

    def score(self, key: str) -> ScoreAnswer:
        return _typed(self.answers, key, ScoreAnswer)


def _typed[A: (NoulAnswer, ChoiceAnswer, ScoreAnswer)](answers: dict[str, Answer], key: str, kind: type[A]) -> A:
    answer = answers.get(key)
    if not isinstance(answer, kind):
        raise JevError(f"answer {key!r} is {type(answer).__name__}, expected {kind.__name__}")
    return answer


def _parse_answer(key: str, raw: dict[str, Any]) -> Answer:
    try:
        kind = raw["type"]
        if kind == "noul":
            return NoulAnswer(p=float(raw["noul"]))
        if kind == "choice":
            return ChoiceAnswer(
                choice=str(raw["choice"]),
                probabilities={str(k): float(v) for k, v in raw["probabilities"].items()},
                confidence=float(raw["confidence"]),
            )
        if kind == "score":
            return ScoreAnswer(
                score=float(raw["score"]),
                probabilities={int(k): float(v) for k, v in raw["probabilities"].items()},
                confidence=float(raw["confidence"]),
                legend={int(k): str(v) for k, v in (raw.get("legend") or {}).items()},
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise JevError(f"malformed answer for {key!r}: {exc}") from exc
    raise JevError(f"unknown answer type {kind!r} for {key!r}")


def _loggable(answers: dict[str, Answer]) -> dict[str, Any]:
    """Every probability, compactly — calibration needs the raw numbers later (§10)."""
    out: dict[str, Any] = {}
    for key, answer in answers.items():
        if isinstance(answer, NoulAnswer):
            out[key] = round(answer.p, 4)
        elif isinstance(answer, ChoiceAnswer):
            out[key] = {"choice": answer.choice, "confidence": round(answer.confidence, 4), "p": answer.probabilities}
        else:
            out[key] = {"score": round(answer.score, 4), "confidence": round(answer.confidence, 4)}
    return out


# ──────────────────────────────────────────────────────────────────────
#  Client
# ──────────────────────────────────────────────────────────────────────


class JevClient:
    """Async client for ``POST /v1/systemone``.

    ``transport`` exists for tests (``httpx.MockTransport``); production leaves it
    ``None``. One ``httpx.AsyncClient`` per instance keeps the connection warm,
    which matters when the whole call is meant to cost ~100 ms.
    """

    def __init__(self, settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=self._settings.jev_base_url,
            timeout=self._settings.jev_timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {self._settings.jev_api_key}"},
        )

    @property
    def enabled(self) -> bool:
        return bool(self._settings.jev_api_key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def judge(self, state: str | dict[str, Any] | list[Any], questions: dict[str, Question]) -> JevResponse:
        """Ask every question about one state in a single parallel call (speculative fan-out, §7.2)."""
        if not self.enabled:
            raise JevUnavailableError("Jev is not configured (JEV_API_KEY unset)")
        if not questions:
            raise JevRequestError("no questions")

        payload = {
            "model": self._settings.jev_model,
            "state": state,
            "questions": {key: q.to_json() for key, q in questions.items()},
        }

        started = time.perf_counter()
        body = await self._post_with_retry(payload)
        latency_ms = (time.perf_counter() - started) * 1000.0

        raw_answers = body.get("answers") or {}
        missing = set(questions) - set(raw_answers)
        if missing:
            raise JevError(f"response is missing answers for {sorted(missing)}")
        answers = {key: _parse_answer(key, raw_answers[key]) for key in questions}

        model = str(body.get("model", ""))
        if model != self._settings.jev_model:
            # Thresholds are calibrated per version. Answer anyway, but loudly.
            logger.warning("jev_model_mismatch", pinned=self._settings.jev_model, answered=model)

        usage = body.get("usage") or {}
        response = JevResponse(
            model=model,
            answers=answers,
            input_tokens=int(usage.get("input_tokens", 0)),
            latency_ms=round(latency_ms, 1),
        )
        logger.info(
            "jev_judged",
            model=response.model,
            questions=len(questions),
            input_tokens=response.input_tokens,
            latency_ms=response.latency_ms,
            answers=_loggable(answers),
        )
        return response

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = self._settings.jev_max_retries + 1
        for attempt in range(attempts):
            try:
                resp = await self._client.post(_ENDPOINT, json=payload)
            except httpx.TimeoutException as exc:
                logger.warning("jev_timeout", timeout_s=self._settings.jev_timeout_seconds)
                raise JevUnavailableError("Jev timed out") from exc
            except httpx.TransportError as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(_BACKOFF_BASE_S * 2**attempt)
                    continue
                raise JevUnavailableError(f"Jev connection failed: {exc}") from exc

            if resp.status_code == 200:
                data: dict[str, Any] = resp.json()
                return data
            if resp.status_code in (401, 403):
                raise JevRequestError("Jev rejected the API key", detail=resp.text[:500])
            if resp.status_code == 422:
                # The body names the offending field; surface it — this is our bug.
                raise JevRequestError("Jev rejected the request (422)", detail=resp.text[:500])
            if resp.status_code in _RETRYABLE and attempt + 1 < attempts:
                delay = _retry_delay(resp, attempt)
                if delay is None:
                    break
                logger.info("jev_retry", status=resp.status_code, attempt=attempt + 1, delay_s=delay)
                await asyncio.sleep(delay)
                continue
            if resp.status_code in _RETRYABLE:
                break
            raise JevRequestError(f"Jev returned HTTP {resp.status_code}", detail=resp.text[:500])
        raise JevUnavailableError("Jev unavailable after retries")


def _retry_delay(resp: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or ``None`` if the server asked for longer than we will wait."""
    header = resp.headers.get("retry-after")
    if header:
        try:
            requested = float(header)
        except ValueError:
            requested = None
        if requested is not None:
            return requested if requested <= _RETRY_AFTER_CAP_S else None
    return float(_BACKOFF_BASE_S * 2**attempt)
