"""ZugaLife life goals Pydantic request/response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


# --- Requests ---


class GoalCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    deadline: date | None = None


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
    milestones: list[MilestoneResponse]
    milestone_count: int = 0
    milestone_done: int = 0


class GoalListResponse(BaseModel):
    active: list[GoalResponse]
    completed: list[GoalResponse]
