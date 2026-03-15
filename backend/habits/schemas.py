"""ZugaLife habit tracking Pydantic request/response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


# Common unit suggestions (not enforced — users can type any unit)
SUGGESTED_UNITS = [
    "hours", "minutes", "glasses", "steps", "servings",
    "pages", "count", "sessions", "reps", "miles", "km",
    "calories", "mg", "oz", "sets", "laps", "chapters",
]


# --- Requests ---


class HabitCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    emoji: str = Field(..., min_length=1, max_length=32)
    unit: str | None = Field(None, max_length=20)
    default_target: float | None = Field(None, gt=0)


class HabitUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    emoji: str | None = Field(None, min_length=1, max_length=32)
    is_active: bool | None = None
    sort_order: int | None = Field(None, ge=0)
    weekly_target: int | None = Field(None, ge=1, le=7)


class HabitLogRequest(BaseModel):
    habit_id: int
    completed: bool = True
    amount: float | None = Field(None, ge=0)
    log_date: date | None = None  # Defaults to today server-side


# --- Responses ---


class HabitDefinitionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    emoji: str
    unit: str | None
    default_target: float | None
    is_preset: bool
    is_active: bool
    sort_order: int
    weekly_target: int | None
    created_at: datetime


class HabitLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    habit_id: int
    log_date: date
    completed: bool
    amount: float | None
    created_at: datetime


class HabitCheckInItem(BaseModel):
    """One habit's status for a given date."""

    habit: HabitDefinitionResponse
    logged: bool
    amount: float | None = None
    log_id: int | None = None


class DailyCheckInResponse(BaseModel):
    date: date
    habits: list[HabitCheckInItem]
    completed_count: int
    total_count: int


class HabitStreakInfo(BaseModel):
    habit_id: int
    habit_name: str
    habit_emoji: str
    current_streak: int
    longest_streak: int


class AllStreaksResponse(BaseModel):
    habits: list[HabitStreakInfo]
    overall_current: int  # days with at least 1 habit logged
    overall_longest: int


class DayHistory(BaseModel):
    date: date
    completed_count: int
    total_active: int
    completion_rate: float
    habits_done: list[str]  # emoji list of completed habits


class HabitHistoryResponse(BaseModel):
    days: list[DayHistory]
    period_days: int


class HabitInsightResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    content: str
    model_used: str
    cost: float
    week_start: date
    created_at: datetime


class HabitInsightListResponse(BaseModel):
    insights: list[HabitInsightResponse]
    total: int


# --- Weekly Targets ---


class WeeklyTargetItem(BaseModel):
    habit_id: int
    habit_name: str
    habit_emoji: str
    weekly_target: int
    this_week_count: int
    progress_pct: float


class WeeklyTargetsResponse(BaseModel):
    habits: list[WeeklyTargetItem]
    week_start: date
