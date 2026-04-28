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


class TherapistSpeakRequest(BaseModel):
    """Request to synthesize an assistant utterance to audio."""
    text: str = Field(..., min_length=1, max_length=2000, description="Assistant text to speak")
    voice: str = Field(default="calm-female", description="Cartesia voice key (see CARTESIA_VOICE_MAP)")


class TherapistTranscribeResponse(BaseModel):
    """Whisper STT result. Audio is sent as multipart, not in this schema."""
    text: str = Field(..., description="Transcribed text")
    duration_sec: float = Field(..., description="Audio duration in seconds (Whisper-reported)")
    cost_usd: float = Field(..., description="USD cost of the transcription call")


class TherapistSpeakResponse(BaseModel):
    """Audio + cost metadata. Audio is delivered as the response body (MP3);
    this schema is only used for the OpenAPI doc and 4xx error envelopes."""
    cost: float = Field(..., description="USD cost of this TTS call")
    duration_ms: int = Field(..., description="Approximate audio duration in milliseconds")
    voice: str = Field(..., description="Echoed Cartesia voice key actually used")


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
