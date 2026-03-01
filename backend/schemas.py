"""ZugaLife Pydantic request/response schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MoodEmoji(str, Enum):
    HAPPY = "\U0001f60a"        # 😊
    SAD = "\U0001f622"          # 😢
    ANGRY = "\U0001f620"        # 😠
    ANXIOUS = "\U0001f630"      # 😰
    TIRED = "\U0001f634"        # 😴
    EXCITED = "\U0001f929"      # 🤩
    NEUTRAL = "\U0001f610"      # 😐
    LOVED = "\U0001f970"        # 🥰
    FRUSTRATED = "\U0001f624"   # 😤
    THOUGHTFUL = "\U0001f914"   # 🤔
    CALM = "\U0001f60c"         # 😌
    MOTIVATED = "\U0001f4aa"    # 💪


EMOJI_TO_LABEL: dict[str, str] = {
    "\U0001f60a": "Happy",
    "\U0001f622": "Sad",
    "\U0001f620": "Angry",
    "\U0001f630": "Anxious",
    "\U0001f634": "Tired",
    "\U0001f929": "Excited",
    "\U0001f610": "Neutral",
    "\U0001f970": "Loved",
    "\U0001f624": "Frustrated",
    "\U0001f914": "Thoughtful",
    "\U0001f60c": "Calm",
    "\U0001f4aa": "Motivated",
}


class MoodLogRequest(BaseModel):
    emoji: MoodEmoji
    note: str | None = Field(None, max_length=500)


class MoodEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: str
    emoji: str
    label: str
    note: str | None
    created_at: datetime


class MoodLogResponse(BaseModel):
    entry: MoodEntryResponse
    streak: int
    today_count: int


class MoodHistoryResponse(BaseModel):
    entries: list[MoodEntryResponse]
    total: int
    days: int


class MoodStreakResponse(BaseModel):
    streak_days: int
    total_logs: int
