"""ZugaLife meditation Pydantic request/response schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# --- Enums ---


class MeditationType(str, Enum):
    breathing = "breathing"
    body_scan = "body_scan"
    loving_kindness = "loving_kindness"
    visualization = "visualization"
    gratitude = "gratitude"
    stress_relief = "stress_relief"


class MeditationLength(str, Enum):
    quick = "quick"    # ~1-3 min (quick reset)
    short = "short"    # ~3-5 min
    medium = "medium"  # ~7-10 min
    long = "long"      # ~12+ min


class AmbienceType(str, Enum):
    rain = "rain"
    ocean = "ocean"
    forest = "forest"
    bowls = "bowls"
    silence = "silence"


class VoiceType(str, Enum):
    # Meditation voice options. When Cartesia is active, these map to Cartesia voice UUIDs
    # via CARTESIA_VOICE_MAP in meditation/routes.py. When Cartesia is not configured,
    # "serene" and "gentle" fall back to OpenAI shimmer, "whisper" falls back to nova.
    serene = "serene"      # Meditation Lady — calm, soothing (default)
    gentle = "gentle"      # Calm Lady — warm, gentle
    whisper = "whisper"    # ASMR Lady — very soft, breathy


# --- Requests ---


class GenerateRequest(BaseModel):
    type: MeditationType
    length: MeditationLength = MeditationLength.medium
    ambience: AmbienceType = AmbienceType.rain
    voice: VoiceType = VoiceType.serene
    focus: str | None = Field(None, max_length=200)


class MoodAfterRequest(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=10)


# --- Responses ---


class SessionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    type: str
    length: str = "medium"
    duration_seconds: int = 0
    ambience: str
    voice: str
    focus: str | None
    title: str
    transcript: str
    audio_filename: str
    model_used: str
    tts_model: str
    cost: float
    status: str = "ready"
    error_message: str | None = Field(None, exclude=True)  # internal only, never sent to client
    mood_before: str | None
    mood_after: str | None
    is_favorite: bool
    completed_at: datetime | None = None
    created_at: datetime

    @field_validator("length", mode="before")
    @classmethod
    def _default_length(cls, v):
        return v if v is not None else "medium"

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def _default_duration(cls, v):
        return v if v is not None else 0


class SessionBrief(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    type: str
    length: str = "medium"
    duration_seconds: int = 0
    title: str
    is_favorite: bool
    mood_after: str | None
    created_at: datetime

    @field_validator("length", mode="before")
    @classmethod
    def _default_length(cls, v):
        return v if v is not None else "medium"

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def _default_duration(cls, v):
        return v if v is not None else 0


class SessionListResponse(BaseModel):
    sessions: list[SessionBrief]
    total: int


class RemainingResponse(BaseModel):
    used: int
    limit: int
    remaining: int
