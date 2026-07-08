"""Optional Langfuse tracing — no-op unless LANGFUSE keys are configured.

Every agent execution becomes an observation and every LLM call a generation
(with token usage), so per-request latency and cost are inspectable in the
Langfuse UI. When the keys are absent the tracer degrades to a no-op, the
same graceful-fallback contract the LLM and shopping integrations follow.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Literal

from langfuse import Langfuse

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

# The non-generation observation kinds Langfuse accepts for spans.
ObservationType = Literal["span", "agent", "tool", "chain", "retriever", "evaluator", "guardrail"]


class Tracer:
    """Thin wrapper around the Langfuse client that no-ops when disabled."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._client: Langfuse | None = None
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_host,
                environment=settings.environment,
            )
            logger.info("langfuse_enabled", host=settings.langfuse_host)
        else:
            logger.info("langfuse_disabled", reason="LANGFUSE keys not set")

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextmanager
    def span(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Open an observation span; yields the Langfuse span or None when disabled."""
        if self._client is None:
            yield None
            return
        with self._client.start_as_current_observation(
            name=name,
            as_type=as_type,
            input=input,
            metadata=metadata,
        ) as span:
            yield span

    @contextmanager
    def generation(
        self,
        name: str,
        *,
        model: str,
        input: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        """Open a generation observation for an LLM call."""
        if self._client is None:
            yield None
            return
        with self._client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=input,
            metadata=metadata,
        ) as generation:
            yield generation

    def flush(self) -> None:
        if self._client is not None:
            self._client.flush()

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.shutdown()


@lru_cache
def get_tracer() -> Tracer:
    """Process-wide tracer singleton."""
    return Tracer()
