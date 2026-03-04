"""ZugaLife journal Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class JournalCreateRequest(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: str = Field(..., min_length=1, max_length=50000)
    mood_emoji: str | None = Field(None, max_length=4)


class JournalReflectionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    content: str
    model_used: str
    cost: float
    created_at: datetime


class JournalEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: str
    title: str | None
    content: str
    mood_emoji: str | None
    mood_label: str | None
    reflections: list[JournalReflectionResponse]
    created_at: datetime
    updated_at: datetime


class JournalEntryBrief(BaseModel):
    """Lightweight version for list views — no full content or reflections."""
    model_config = {"from_attributes": True}

    id: int
    title: str | None
    content_preview: str  # first 200 chars
    mood_emoji: str | None
    mood_label: str | None
    reflection_count: int
    created_at: datetime


class JournalListResponse(BaseModel):
    entries: list[JournalEntryBrief]
    total: int


class JournalReflectResponse(BaseModel):
    reflection: JournalReflectionResponse
    remaining: int  # how many more reflections allowed
