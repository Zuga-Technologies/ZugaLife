"""Pydantic response schemas for mood forecasting."""

from __future__ import annotations

from pydantic import BaseModel


class TrendResult(BaseModel):
    slope: float
    direction: str
    description: str
    avg_valence: float | None = None
    data_points: int | None = None


class DayOfWeekEntry(BaseModel):
    day: str
    avg_valence: float | None
    entries: int


class DayOfWeekResult(BaseModel):
    days: list[DayOfWeekEntry]
    description: str


class ForecastResult(BaseModel):
    forecast_valence: float | None
    forecast_label: str | None
    confidence: str
    method: str | None = None
    description: str


class HabitCorrelation(BaseModel):
    habit_name: str
    habit_emoji: str
    avg_mood_with: float
    avg_mood_without: float
    delta: float
    days_with: int
    days_without: int


class HabitCorrelationsResult(BaseModel):
    habits: list[HabitCorrelation]
    description: str


class VolatilityResult(BaseModel):
    current_volatility: float | None
    previous_volatility: float | None = None
    change: float | None = None
    direction: str
    level: str | None = None
    description: str


class MeditationEffectivenessResult(BaseModel):
    avg_delta: float | None
    sessions_analyzed: int
    improved: int | None = None
    unchanged: int | None = None
    worsened: int | None = None
    description: str


class ArimaDayForecast(BaseModel):
    date: str
    forecast_valence: float
    forecast_label: str


class ArimaWeekEntry(BaseModel):
    date: str
    day: str
    forecast_valence: float
    forecast_label: str


class ArimaForecastResponse(BaseModel):
    next_day: ArimaDayForecast | None
    next_7_days: list[ArimaWeekEntry]
    confidence: str
    data_days: int | None = None
    description: str
    method: str = "arima"


class ArimaxForecastResponse(BaseModel):
    next_day: ArimaDayForecast | None
    next_7_days: list[ArimaWeekEntry]
    confidence: str
    data_days: int | None = None
    exogenous_factors: list[str] = []
    description: str
    method: str = "arimax"


class MoodForecastResponse(BaseModel):
    period_days: int
    total_entries: int
    trend: TrendResult
    day_of_week: DayOfWeekResult
    forecast: ForecastResult
    habit_correlations: HabitCorrelationsResult
    volatility: VolatilityResult
    meditation_effectiveness: MeditationEffectivenessResult
