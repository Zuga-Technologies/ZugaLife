"""ZugaLife mood logging endpoints."""

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules are pre-loaded by plugin.py into sys.modules before
# this module executes. We pull classes into globals so FastAPI can
# resolve type annotations at decoration time.
_models = sys.modules["zugalife.models"]
_schemas = sys.modules["zugalife.schemas"]

def _get_gam_engine():
    """Lazy lookup — gamification loads after mood routes in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

MoodEntry = _models.MoodEntry
MoodLogRequest = _schemas.MoodLogRequest
MoodLogResponse = _schemas.MoodLogResponse
MoodEntryResponse = _schemas.MoodEntryResponse
MoodHistoryResponse = _schemas.MoodHistoryResponse
MoodStreakResponse = _schemas.MoodStreakResponse
MoodSuggestion = _schemas.MoodSuggestion
EMOJI_TO_LABEL = _schemas.EMOJI_TO_LABEL

# Valence scores for breathwork intervention trigger (negative = suggest breathwork)
_MOOD_VALENCE: dict[str, int] = {
    "Happy": 2, "Excited": 3, "Loved": 2, "Motivated": 3,
    "Calm": 1, "Thoughtful": 0, "Neutral": 0, "Tired": -1,
    "Sad": -2, "Frustrated": -2, "Anxious": -2, "Angry": -3,
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/life", tags=["life"])


@router.post("/mood", response_model=MoodLogResponse)
async def log_mood(
    body: MoodLogRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Log a mood entry. Rate-limited to 1 entry per 6-hour window."""
    async with get_session() as session:
        # Enforce cooldown: max 1 entry per 6-hour rolling window
        window_start = datetime.now(timezone.utc) - timedelta(hours=6)
        count_result = await session.execute(
            select(func.count())
            .select_from(MoodEntry)
            .where(
                MoodEntry.user_id == user.id,
                MoodEntry.created_at >= window_start,
            )
        )
        recent_count = count_result.scalar_one()

        if recent_count >= 1:
            # Find the oldest entry in the window to calculate next available
            oldest_result = await session.execute(
                select(MoodEntry.created_at)
                .where(
                    MoodEntry.user_id == user.id,
                    MoodEntry.created_at >= window_start,
                )
                .order_by(MoodEntry.created_at)
                .limit(1)
            )
            oldest_time = oldest_result.scalar_one()
            # SQLite may strip timezone — ensure UTC
            if oldest_time.tzinfo is None:
                oldest_time = oldest_time.replace(tzinfo=timezone.utc)
            next_available = oldest_time + timedelta(hours=6)
            raise HTTPException(
                status_code=429,
                detail=f"Cooldown active. Next log available at {next_available.isoformat()}",
            )

        # Create the mood entry
        label = EMOJI_TO_LABEL[body.emoji.value]
        entry = MoodEntry(
            user_id=user.id,
            emoji=body.emoji.value,
            label=label,
            note=body.note,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)

        # Calculate streak
        streak = await _calculate_streak(session, user.id)

        # Count today's entries
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        today_result = await session.execute(
            select(func.count())
            .select_from(MoodEntry)
            .where(
                MoodEntry.user_id == user.id,
                MoodEntry.created_at >= today_start,
            )
        )
        today_count = today_result.scalar_one()

        # Emit webhook event (fire-and-forget)
        try:
            from core.events.proxy import emit
            asyncio.create_task(emit("life:mood_logged", {
                "emoji": body.emoji.value,
                "label": label,
                "note": body.note or "",
                "streak": streak,
            }, user_id=user.id))
        except Exception:
            pass  # Never block mood logging on event emission

        # Suggest breathwork for negative moods (valence <= -2)
        suggestion = None
        valence = _MOOD_VALENCE.get(label, 0)
        if valence <= -2:
            suggestion = MoodSuggestion(
                type="breathwork",
                message="A 2-minute breathing exercise can help shift how you feel right now.",
            )

        response = MoodLogResponse(
            entry=MoodEntryResponse.model_validate(entry),
            streak=streak,
            today_count=today_count,
            suggestion=suggestion,
        )

        gam = _get_gam_engine()
        if gam:
            try:
                await gam.award_xp(
                    session, user_id=user.id,
                    source="mood_log",
                    description=f"Logged mood: {label}",
                )
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

    return response


@router.get("/mood", response_model=MoodHistoryResponse)
async def get_history(
    days: int = Query(7, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
):
    """Get mood history for the last N days."""
    async with get_session() as session:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await session.execute(
            select(MoodEntry)
            .where(
                MoodEntry.user_id == user.id,
                MoodEntry.created_at >= since,
            )
            .order_by(desc(MoodEntry.created_at))
        )
        entries = result.scalars().all()

    return MoodHistoryResponse(
        entries=[MoodEntryResponse.model_validate(e) for e in entries],
        total=len(entries),
        days=days,
    )


@router.get("/mood/streak", response_model=MoodStreakResponse)
async def get_streak(
    user: CurrentUser = Depends(get_current_user),
):
    """Get current consecutive-day streak and total log count."""
    async with get_session() as session:
        streak = await _calculate_streak(session, user.id)

        total_result = await session.execute(
            select(func.count())
            .select_from(MoodEntry)
            .where(MoodEntry.user_id == user.id)
        )
        total_logs = total_result.scalar_one()

    return MoodStreakResponse(
        streak_days=streak,
        total_logs=total_logs,
    )


async def _calculate_streak(session, user_id: str) -> int:
    """Count consecutive days with at least one mood entry, ending today.

    Uses the user's configured timezone so streaks reset at the user's
    local midnight — not UTC midnight. Earlier versions delegated date
    extraction to `func.date(created_at)` which returns the UTC date in
    SQLite/Postgres; that broke evening logs (8pm EST = 1am UTC next day),
    causing streaks to silently undercount or stick at small numbers
    regardless of how many consecutive days the user actually logged.

    The fix: pull every timestamp, convert each to the user's local date
    in Python, then count consecutive days from today backwards. Mood
    entries are sparse (≤ a few per day per user) so the read isn't
    expensive.
    """
    import zoneinfo
    from zoneinfo import ZoneInfo

    LifeUserSettings = sys.modules["zugalife.settings_models"].LifeUserSettings

    tz_result = await session.execute(
        select(LifeUserSettings.timezone).where(LifeUserSettings.user_id == user_id)
    )
    tz_name = tz_result.scalar_one_or_none() or "America/New_York"
    try:
        user_tz = ZoneInfo(tz_name)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        user_tz = ZoneInfo("America/New_York")

    today = datetime.now(user_tz).date()

    result = await session.execute(
        select(MoodEntry.created_at)
        .where(MoodEntry.user_id == user_id)
        .order_by(desc(MoodEntry.created_at))
    )
    timestamps = [row[0] for row in result.all()]
    if not timestamps:
        return 0

    # Stored timestamps may be naive (SQLite strips tzinfo). Treat naive as
    # UTC — that's what the model writes.
    local_dates = set()
    for ts in timestamps:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local_dates.add(ts.astimezone(user_tz).date())

    sorted_dates = sorted(local_dates, reverse=True)

    # Streak must include today (strict — no grace period)
    if sorted_dates[0] != today:
        return 0

    streak = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i - 1] - sorted_dates[i] == timedelta(days=1):
            streak += 1
        else:
            break

    return streak
