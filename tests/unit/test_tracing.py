"""Tests for the optional Langfuse tracer (no-op contract when disabled)."""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.tracing import Tracer


def _disabled_tracer() -> Tracer:
    return Tracer(settings=Settings(langfuse_public_key="", langfuse_secret_key=""))


class TestDisabledTracer:
    def test_disabled_without_keys(self) -> None:
        tracer = _disabled_tracer()
        assert tracer.enabled is False

    def test_span_yields_none(self) -> None:
        tracer = _disabled_tracer()
        with tracer.span("agent.test", as_type="agent") as span:
            assert span is None

    def test_generation_yields_none(self) -> None:
        tracer = _disabled_tracer()
        with tracer.generation("llm.test", model="deepseek-chat", input="hi") as generation:
            assert generation is None

    def test_span_propagates_exceptions(self) -> None:
        tracer = _disabled_tracer()
        try:
            with tracer.span("agent.test"):
                raise ValueError("boom")
        except ValueError as exc:
            assert str(exc) == "boom"
        else:  # pragma: no cover
            raise AssertionError("exception was swallowed")

    def test_flush_and_shutdown_are_safe(self) -> None:
        tracer = _disabled_tracer()
        tracer.flush()
        tracer.shutdown()
