"""Mood forecasting API endpoint — pure statistics, computed on-demand."""

import sys

from fastapi import APIRouter, Depends, Query

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

_engine = sys.modules["zugalife.forecasting.engine"]
_schemas = sys.modules["zugalife.forecasting.schemas"]

MoodForecastResponse = _schemas.MoodForecastResponse
ArimaForecastResponse = _schemas.ArimaForecastResponse

router = APIRouter(prefix="/api/life", tags=["life-forecasting"])


@router.get("/mood/forecast", response_model=MoodForecastResponse)
async def get_mood_forecast(
    days: int = Query(30, ge=7, le=365, description="Analysis window in days"),
    user: CurrentUser = Depends(get_current_user),
):
    """Compute mood analytics: trend, patterns, forecast, correlations.

    Pure statistics — no AI calls, no stored predictions.
    Minimum 7-day window to produce meaningful results.
    """
    async with get_session() as session:
        result = await _engine.compute_all(session, user.id, days)

    return result


@router.get("/mood/forecast/arima", response_model=ArimaForecastResponse)
async def get_arima_forecast(
    days: int = Query(30, ge=7, le=365, description="Analysis window in days"),
    user: CurrentUser = Depends(get_current_user),
):
    """ARIMA-based mood forecast — next day and 7-day prediction.

    Uses ARIMA(1,1,1) on daily average valence scores.
    Requires at least 7 mood entries across 7 different days.
    """
    async with get_session() as session:
        entries = await _engine._fetch_mood_entries(session, user.id, days)

    return _engine.compute_arima_forecast(entries)
