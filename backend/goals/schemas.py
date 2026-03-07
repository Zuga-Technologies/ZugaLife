"""ZugaLife life goals Pydantic request/response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


# --- Requests ---


class GoalCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    deadline: date | None = None


class GoalFromTemplateRequest(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=50)


class GoalUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    deadline: date | None = None
    sort_order: int | None = Field(None, ge=0)


class MilestoneCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class MilestoneUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    is_completed: bool | None = None
    sort_order: int | None = Field(None, ge=0)


class HabitLinkRequest(BaseModel):
    habit_id: int


# --- Responses ---


class MilestoneResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    goal_id: int
    title: str
    is_completed: bool
    sort_order: int
    created_at: datetime
    completed_at: datetime | None


class LinkedHabitResponse(BaseModel):
    habit_id: int
    habit_name: str
    habit_emoji: str
    days_completed: int  # out of last 7 days
    days_total: int  # 7


class GoalResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str | None
    deadline: date | None
    is_completed: bool
    sort_order: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    template_key: str | None = None
    milestones: list[MilestoneResponse]
    milestone_count: int = 0
    milestone_done: int = 0
    linked_habits: list[LinkedHabitResponse] = []


class GoalListResponse(BaseModel):
    active: list[GoalResponse]
    completed: list[GoalResponse]


class GoalTemplateResponse(BaseModel):
    key: str
    title: str
    description: str
    suggested_habits: list[str]  # habit names that match presets
    already_adopted: bool = False
