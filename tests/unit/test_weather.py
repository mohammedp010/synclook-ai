"""Open-Meteo weather: geocode → forecast → Weather, cached per place per day; any failure is None."""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from backend.engine.outfits import TempBand, Weather
from backend.services.weather import FORECAST_URL, GEOCODE_URL, WeatherService


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.store[key] = value


def _client(calls: list[str], *, rain: int = 80, fail: bool = False) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url.copy_with(query=None)))
        if fail:
            return httpx.Response(503)
        if str(request.url).startswith(GEOCODE_URL):
            return httpx.Response(200, json={"results": [{"latitude": 19.07, "longitude": 72.88}]})
        return httpx.Response(
            200,
            json={
                "daily": {
                    "temperature_2m_max": [33.0],
                    "temperature_2m_min": [23.0],
                    "precipitation_probability_max": [rain],
                }
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_place_is_geocoded_then_forecast_and_both_are_cached() -> None:
    calls: list[str] = []
    cache = FakeCache()
    service = WeatherService(cache=cache, client=_client(calls))  # type: ignore[arg-type]
    day = dt.date(2026, 11, 15)
    weather = await service.forecast(place="Mumbai", day=day)
    assert weather == Weather(temperature_c=28.0, rain=True)
    assert weather.band == TempBand.HOT
    assert calls == [GEOCODE_URL, FORECAST_URL]
    assert await service.forecast(place="mumbai ", day=day) == weather
    assert len(calls) == 2  # second answer came from the cache
    assert "weather:19.07,72.88:2026-11-15" in cache.store


async def test_coordinates_skip_the_geocoder() -> None:
    calls: list[str] = []
    weather = await WeatherService(client=_client(calls, rain=10)).forecast(latitude=1.0, longitude=2.0)
    assert weather is not None and not weather.rain
    assert calls == [FORECAST_URL]


async def test_any_failure_is_none_not_an_error() -> None:
    assert await WeatherService(client=_client([], fail=True)).forecast(place="Mumbai") is None
    assert await WeatherService(client=_client([])).forecast() is None


def test_bands() -> None:
    assert Weather(11.9, False).band == TempBand.COLD
    assert Weather(12, False).band == TempBand.MILD
    assert Weather(26, False).band == TempBand.HOT
    assert Weather(20, True).wants_outerwear and Weather(5, False).wants_outerwear
    assert not Weather(20, False).wants_outerwear
