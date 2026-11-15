"""Tests never touch Postgres: the kv_cache (daily spend caps, caches) is a dict per test, and the
in-memory rate limits start empty for each test."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from backend.core import rate_limit
from backend.services.cache import KvCache


@pytest.fixture(autouse=True)
def memory_cache_and_fresh_limits(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    data: dict[str, Any] = {}

    async def get(_self: KvCache, key: str) -> Any:
        return data.get(key)

    async def set_(_self: KvCache, key: str, value: Any, ttl_seconds: int) -> None:
        data[key] = value

    monkeypatch.setattr(KvCache, "get", get)
    monkeypatch.setattr(KvCache, "set", set_)
    rate_limit.limiter.reset()
    rate_limit._mcp.storage.reset()
    yield data
