"""ZugaLife mood logging endpoints."""

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

MoodEntry = _models.MoodEntry
MoodLogRequest = _schemas.MoodLogRequest
MoodLogResponse = _schemas.MoodLogResponse
MoodEntryResponse = _schemas.MoodEntryResponse
MoodHistoryResponse = _schemas.MoodHistoryResponse
MoodStreakResponse = _schemas.MoodStreakResponse
EMOJI_TO_LABEL = _schemas.EMOJI_TO_LABEL

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

        response = MoodLogResponse(
            entry=MoodEntryResponse.model_validate(entry),
            streak=streak,
            today_count=today_count,
        )

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

    Uses the user's configured timezone so streaks reset at the
    user's local midnight — not UTC midnight.
    """
    _helpers = sys.modules["zugalife.settings_helpers"]
    today = await _helpers.get_user_today(session, user_id)

    result = await session.execute(
        select(func.date(MoodEntry.created_at))
        .where(MoodEntry.user_id == user_id)
        .group_by(func.date(MoodEntry.created_at))
        .order_by(desc(func.date(MoodEntry.created_at)))
    )
    log_dates = [row[0] for row in result.all()]

    if not log_dates:
        return 0

    # Parse if SQLite returned strings
    def _to_date(d):
        return date.fromisoformat(d) if isinstance(d, str) else d

    first = _to_date(log_dates[0])

    # Streak must include today (strict — no grace period)
    if first != today:
        return 0

    streak = 1
    for i in range(1, len(log_dates)):
        current = _to_date(log_dates[i])
        previous = _to_date(log_dates[i - 1])
        if previous - current == timedelta(days=1):
            streak += 1
        else:
            break

    return streak
