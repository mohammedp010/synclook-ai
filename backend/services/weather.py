"""Weather for "what do I wear?": Open-Meteo (free, no key) → ``engine.outfits.Weather``.

A place name is geocoded first. Both answers are cached in ``kv_cache`` (places for
30 days, forecasts per place per day for a day). Any failure returns None: outfits
are then built without weather rather than not built.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from backend.core.logging import get_logger
from backend.engine.outfits import Weather
from backend.services.cache import KvCache

logger = get_logger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
RAIN_FROM_PERCENT = 50
_TIMEOUT_S = 5.0
_DAY_S = 86_400


class WeatherService:
    def __init__(self, cache: KvCache | None = None, client: httpx.AsyncClient | None = None) -> None:
        self._cache = cache
        self._client = client

    async def _get(self, url: str, params: dict[str, str | float]) -> dict[str, object]:
        if self._client is not None:
            response = await self._client.get(url, params=params, timeout=_TIMEOUT_S)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=_TIMEOUT_S)
        response.raise_for_status()
        body: dict[str, object] = response.json()
        return body

    async def _cached(self, key: str, ttl: int, fetch: Callable[[], Awaitable[Any]]) -> Any:
        if self._cache is not None and (hit := await self._cache.get(key)) is not None:
            return hit
        value = await fetch()
        if self._cache is not None:
            await self._cache.set(key, value, ttl)
        return value

    async def locate(self, place: str) -> tuple[float, float] | None:
        async def fetch() -> list[float] | None:
            body = await self._get(GEOCODE_URL, {"name": place, "count": 1})
            results = body.get("results")
            if not isinstance(results, list) or not results:
                return None
            return [float(results[0]["latitude"]), float(results[0]["longitude"])]

        found = await self._cached(f"geo:{place.strip().lower()}", 30 * _DAY_S, fetch)
        return (found[0], found[1]) if isinstance(found, list) else None

    async def forecast(
        self,
        *,
        place: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        day: dt.date | None = None,
    ) -> Weather | None:
        """The day's mean temperature and rain (probability ≥ 50%), or None on any failure."""
        try:
            if latitude is None or longitude is None:
                spot = await self.locate(place) if place else None
                if spot is None:
                    return None
                latitude, longitude = spot
            when = (day or dt.date.today()).isoformat()

            async def fetch() -> list[float]:
                body = await self._get(
                    FORECAST_URL,
                    {
                        "latitude": latitude,
                        "longitude": longitude,
                        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                        "timezone": "auto",
                        "start_date": when,
                        "end_date": when,
                    },
                )
                daily = body["daily"]
                assert isinstance(daily, dict)
                rain = daily["precipitation_probability_max"][0]
                return [
                    (float(daily["temperature_2m_max"][0]) + float(daily["temperature_2m_min"][0])) / 2,
                    float(rain if rain is not None else 0),
                ]

            key = f"weather:{latitude:.2f},{longitude:.2f}:{when}"
            mean_c, rain_p = await self._cached(key, _DAY_S, fetch)
            return Weather(temperature_c=round(mean_c, 1), rain=rain_p >= RAIN_FROM_PERCENT)
        except Exception as exc:  # weather is optional: never fail the outfit request over it
            logger.warning("weather_unavailable", error=str(exc), place=place)
            return None
