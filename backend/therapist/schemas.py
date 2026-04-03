"""ZugaLife therapist request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Requests ---


class TherapistMessage(BaseModel):
    """A single message in therapist conversation. Only user/assistant roles allowed."""
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=10_000)


class TherapistChatRequest(BaseModel):
    messages: list[TherapistMessage] = Field(..., min_length=1)


class TherapistEndSessionRequest(BaseModel):
    messages: list[TherapistMessage] = Field(..., min_length=1)
    mood_before: str | None = Field(None, max_length=32)
    mood_after: str | None = Field(None, max_length=32)
    rating: int | None = Field(None, ge=1, le=5)


class SessionNoteUpdateRequest(BaseModel):
    themes: str | None = Field(None, min_length=1, max_length=5000)
    patterns: str | None = Field(None, max_length=5000)
    follow_up: str | None = Field(None, max_length=5000)


# --- Responses ---


class TherapistChatResponse(BaseModel):
    content: str
    message_index: int
    session_messages_remaining: int
    cost: float
    crisis_detected: bool = False


class SessionNoteResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    themes: str
    patterns: str | None
    follow_up: str | None
    mood_snapshot: str | None
    mood_before: str | None
    mood_after: str | None
    rating: int | None
    message_count: int
    cost: float
    provider: str
    created_at: datetime
    updated_at: datetime


class SessionNoteListResponse(BaseModel):
    notes: list[SessionNoteResponse]
    total: int


class TherapistStatusResponse(BaseModel):
    sessions_used: int
    sessions_limit: int
    sessions_remaining: int
    is_first_session: bool


class ConversationStarter(BaseModel):
    text: str
    source: str  # "mood", "habit", "journal", "general"


class TherapistStartersResponse(BaseModel):
    starters: list[ConversationStarter]
