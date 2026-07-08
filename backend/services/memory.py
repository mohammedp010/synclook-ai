"""Memory Service — Redis-backed user preference and analysis history store.

Stores per-user data:
- Color preferences (liked/disliked colors from feedback)
- Style preferences (liked/disliked styles)
- Recent analysis history (last N detected attributes)

The Orchestrator feeds memory context into the pipeline so
downstream agents can boost recommendations matching user history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

# Redis key prefixes
_PREFIX = "synclook"
_PREFS_KEY = f"{_PREFIX}:prefs:{{user_id}}"
_HISTORY_KEY = f"{_PREFIX}:history:{{user_id}}"

# Defaults
MAX_HISTORY = 10  # keep last N analyses per user


class UserPreferences:
    """In-memory snapshot of a user's stored preferences."""

    __slots__ = ("liked_colors", "disliked_colors", "liked_styles", "disliked_styles")

    def __init__(
        self,
        liked_colors: list[str] | None = None,
        disliked_colors: list[str] | None = None,
        liked_styles: list[str] | None = None,
        disliked_styles: list[str] | None = None,
    ) -> None:
        self.liked_colors = liked_colors or []
        self.disliked_colors = disliked_colors or []
        self.liked_styles = liked_styles or []
        self.disliked_styles = disliked_styles or []

    def to_dict(self) -> dict:
        return {
            "liked_colors": self.liked_colors,
            "disliked_colors": self.disliked_colors,
            "liked_styles": self.liked_styles,
            "disliked_styles": self.disliked_styles,
        }

    @classmethod
    def from_dict(cls, data: dict) -> UserPreferences:
        return cls(
            liked_colors=data.get("liked_colors", []),
            disliked_colors=data.get("disliked_colors", []),
            liked_styles=data.get("liked_styles", []),
            disliked_styles=data.get("disliked_styles", []),
        )


class MemoryService:
    """Redis-backed memory for user preferences and analysis history."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._settings.redis_url,
                decode_responses=True,
            )
            logger.info("memory_redis_connected", url=self._settings.redis_url)
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    # ── User Preferences ─────────────────────────────────────────────

    async def get_preferences(self, user_id: str) -> UserPreferences:
        """Load user preferences from Redis."""
        r = await self._get_redis()
        key = _PREFS_KEY.format(user_id=user_id)
        raw = await r.get(key)
        if raw is None:
            return UserPreferences()
        return UserPreferences.from_dict(json.loads(raw))

    async def save_preferences(self, user_id: str, prefs: UserPreferences) -> None:
        """Persist user preferences to Redis with TTL."""
        r = await self._get_redis()
        key = _PREFS_KEY.format(user_id=user_id)
        await r.set(key, json.dumps(prefs.to_dict()), ex=self._settings.redis_ttl_seconds)
        logger.info("preferences_saved", user_id=user_id)

    async def record_feedback(
        self,
        user_id: str,
        *,
        feedback_type: str,
        colors: list[str],
        styles: list[str],
    ) -> None:
        """Update preferences based on user feedback (like/dislike)."""
        prefs = await self.get_preferences(user_id)

        for color in colors:
            if feedback_type == "like":
                if color not in prefs.liked_colors:
                    prefs.liked_colors.append(color)
                if color in prefs.disliked_colors:
                    prefs.disliked_colors.remove(color)
            elif feedback_type == "dislike":
                if color not in prefs.disliked_colors:
                    prefs.disliked_colors.append(color)
                if color in prefs.liked_colors:
                    prefs.liked_colors.remove(color)

        for style in styles:
            if feedback_type == "like":
                if style not in prefs.liked_styles:
                    prefs.liked_styles.append(style)
                if style in prefs.disliked_styles:
                    prefs.disliked_styles.remove(style)
            elif feedback_type == "dislike":
                if style not in prefs.disliked_styles:
                    prefs.disliked_styles.append(style)
                if style in prefs.liked_styles:
                    prefs.liked_styles.remove(style)

        await self.save_preferences(user_id, prefs)

    # ── Analysis History ─────────────────────────────────────────────

    async def save_analysis(
        self,
        user_id: str,
        *,
        clothing_type: str,
        color: str,
        style: str,
        pattern: str,
    ) -> None:
        """Append an analysis result to the user's history (capped at MAX_HISTORY)."""
        r = await self._get_redis()
        key = _HISTORY_KEY.format(user_id=user_id)
        entry = json.dumps({
            "clothing_type": clothing_type,
            "color": color,
            "style": style,
            "pattern": pattern,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await r.lpush(key, entry)
        await r.ltrim(key, 0, MAX_HISTORY - 1)
        await r.expire(key, self._settings.redis_ttl_seconds)

    async def get_history(self, user_id: str) -> list[dict]:
        """Return the user's recent analysis history (newest first)."""
        r = await self._get_redis()
        key = _HISTORY_KEY.format(user_id=user_id)
        items = await r.lrange(key, 0, MAX_HISTORY - 1)
        return [json.loads(item) for item in items]
