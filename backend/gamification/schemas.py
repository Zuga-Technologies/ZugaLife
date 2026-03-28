"""ZugaLife gamification Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel


class BadgeResponse(BaseModel):
    badge_key: str
    title: str
    description: str
    emoji: str
    earned_at: datetime | None = None


class XPStatusResponse(BaseModel):
    total_xp: int
    level: int
    level_name: str
    xp_for_next_level: int
    xp_progress_in_level: int
    current_streak_days: int
    longest_streak_days: int
    streak_multiplier: float
    prestige_level: int = 0
    prestige_multiplier: float = 1.0
    can_prestige: bool = False


class XPGainResponse(BaseModel):
    xp_gained: int
    new_total: int
    level_up: bool
    new_level: int | None
    new_badges: list[BadgeResponse]


class PrestigeResponse(BaseModel):
    new_prestige_level: int
    prestige_multiplier: float
    badge: BadgeResponse


class DailyChallengeResponse(BaseModel):
    challenge_key: str
    title: str
    description: str
    xp_reward: int
    is_completed: bool
    is_ai_generated: bool = False


class WeeklyQuestResponse(BaseModel):
    quest_key: str
    title: str
    description: str
    xp_reward: int
    is_completed: bool


class AwardXPRequest(BaseModel):
    source: str
    description: str
    base_amount: int | None = None  # Optional override; engine uses the table default


class GamificationDashboard(BaseModel):
    xp: XPStatusResponse
    badges: list[BadgeResponse]
    recent_xp: list[dict]
    daily_challenges: list[DailyChallengeResponse]
    weekly_quests: list[WeeklyQuestResponse]
