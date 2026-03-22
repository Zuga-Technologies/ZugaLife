"""ZugaLife meditation Pydantic request/response schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Enums ---


class MeditationType(str, Enum):
    breathing = "breathing"
    body_scan = "body_scan"
    loving_kindness = "loving_kindness"
    visualization = "visualization"
    gratitude = "gratitude"
    stress_relief = "stress_relief"


class MeditationLength(str, Enum):
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
    shimmer = "shimmer"
    nova = "nova"


# --- Requests ---


class GenerateRequest(BaseModel):
    type: MeditationType
    length: MeditationLength = MeditationLength.medium
    ambience: AmbienceType = AmbienceType.rain
    voice: VoiceType = VoiceType.shimmer
    focus: str | None = Field(None, max_length=200)


class MoodAfterRequest(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=10)


# --- Responses ---


class SessionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    type: str
    length: str
    duration_seconds: int
    ambience: str
    voice: str
    focus: str | None
    title: str
    transcript: str
    audio_filename: str
    model_used: str
    tts_model: str
    cost: float
    mood_before: str | None
    mood_after: str | None
    is_favorite: bool
    created_at: datetime


class SessionBrief(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    type: str
    length: str
    duration_seconds: int
    title: str
    is_favorite: bool
    mood_after: str | None
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionBrief]
    total: int


class RemainingResponse(BaseModel):
    used: int
    limit: int
    remaining: int
