"""What do I wear? Closet + occasion + weather → the engine's top 3 outfits, each explained."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.routes.closet import Cache, Db, UserId, image_url
from backend.core import budget
from backend.core.config import get_settings
from backend.core.dependencies import get_llm_service, get_weather_service
from backend.core.exceptions import LLMError
from backend.schemas.api import OutfitOut, OutfitPiece, OutfitsRequest, OutfitsResponse, WeatherOut
from backend.schemas.taxonomy import Occasion
from backend.services.llm import LLMService
from backend.services.outfit_explainer import Explanation, explain, template
from backend.services.weather import WeatherService
from backend.toolkit import closet_outfits

router = APIRouter()

_CHOICES = ", ".join(o.value for o in Occasion)


async def resolve_occasion(text: str, llm: LLMService, cache: Cache) -> tuple[Occasion, bool]:
    """An exact Occasion value costs nothing; anything else is one text-model call (daily-capped)."""
    key = text.strip().lower().replace(" ", "_").replace("-", "_")
    if key in Occasion._value2member_map_:
        return Occasion(key), False
    try:
        await budget.spend(cache, "outfit_explanations", get_settings().explanation_daily_cap)
    except budget.BudgetExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Demo budget used for today, so free text cannot be read; send one of: {_CHOICES}",
        ) from exc
    try:
        intent = await llm.extract_intent(text)
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not read the occasion; send one of: {_CHOICES}"
        ) from exc
    if intent.occasion_type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No occasion found in that text; send one of: {_CHOICES}"
        )
    return intent.occasion_type, True


@router.post("/outfits")
async def outfits(
    request: OutfitsRequest,
    user_id: UserId,
    db: Db,
    cache: Cache,
    llm: Annotated[LLMService, Depends(get_llm_service)],
    weather_service: Annotated[WeatherService, Depends(get_weather_service)],
) -> OutfitsResponse:
    occasion, from_text = await resolve_occasion(request.occasion, llm, cache)
    weather, notes = None, []
    if request.place or (request.latitude is not None and request.longitude is not None):
        weather = await weather_service.forecast(
            place=request.place, latitude=request.latitude, longitude=request.longitude, day=request.date
        )
        if weather is None:
            notes.append("Weather was unavailable; these outfits ignore it")

    result = await closet_outfits(db, user_id, occasion, weather, request.date or dt.date.today())
    try:
        if result.outfits:
            await budget.spend(cache, "outfit_explanations", get_settings().explanation_daily_cap)
        explanations = await explain(llm, result.outfits, occasion, weather.describe() if weather else None)
    except budget.BudgetExceededError:  # the outfits are rules; only their wording costs money
        explanations = [Explanation(template(o, occasion), "template") for o in result.outfits]
        notes.append("Demo budget for model-written explanations is used up today; these are rule-based.")

    return OutfitsResponse(
        occasion=occasion,
        occasion_from_text=from_text,
        weather=WeatherOut(temperature_c=weather.temperature_c, band=weather.band.value, rain=weather.rain)
        if weather
        else None,
        outfits=[
            OutfitOut(
                items=[
                    OutfitPiece(
                        id=uuid.UUID(i.id),
                        short_label=i.short_label,
                        garment_type=i.garment_type,
                        category=i.category,
                        image_url=image_url(i.id),
                    )
                    for i in o.items
                ],
                score=o.score,
                score_parts=o.score_parts,
                evidence=list(o.evidence),
                explanation=e.text,
                explanation_source=e.source,
            )
            for o, e in zip(result.outfits, explanations, strict=True)
        ],
        reason=result.reason,
        notes=notes + result.notes,
    )
