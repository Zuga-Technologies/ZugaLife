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
    streak_freezes: int = 0
    streak_freeze_used: bool = False
    bonus_label: str | None = None
    bonus_tier: str | None = None
    # Soft streak reframing — consistency rate (Lally: missed days don't reset formation)
    consistency_30d: int = 0       # Days active in last 30
    consistency_pct: float = 0.0   # Percentage (0-100)


class XPGainResponse(BaseModel):
    xp_gained: int
    new_total: int
    level_up: bool
    new_level: int | None
    new_badges: list[BadgeResponse]
    bonus_label: str | None = None
    bonus_tier: str | None = None
    bonus_multiplier: float | None = None
    streak_freeze_used: bool = False


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
    is_ai_generated: bool | None = False
    goal_connection: str | None = None


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
