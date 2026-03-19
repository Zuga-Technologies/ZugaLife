"""ZugaLife dashboard — aggregated overview endpoint.

Single read-only endpoint that pulls key metrics from all modules
for the frontend dashboard. No models needed — pure aggregation.
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

router = APIRouter(prefix="/api/life", tags=["life-dashboard"])


@router.get("/dashboard")
async def get_dashboard(
    user: CurrentUser = Depends(get_current_user),
):
    """Aggregated dashboard data — one call, all modules."""
    import zoneinfo
    from zoneinfo import ZoneInfo

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    async with get_session() as session:
        # Load user settings for timezone + display_name
        LifeUserSettings = sys.modules["zugalife.settings_models"].LifeUserSettings
        settings_result = await session.execute(
            select(LifeUserSettings).where(LifeUserSettings.user_id == user.id)
        )
        settings = settings_result.scalar_one_or_none()

        tz_name = settings.timezone if settings else "America/New_York"
        try:
            user_tz = ZoneInfo(tz_name)
        except (KeyError, zoneinfo.ZoneInfoNotFoundError):
            user_tz = ZoneInfo("America/New_York")

        user_now = datetime.now(user_tz)
        today = user_now.date()
        week_start = today - timedelta(days=today.weekday())  # Monday

        mood = await _mood_metrics(session, user.id, week_ago)
        habits = await _habit_metrics(session, user.id, week_start, today)
        goals = await _goal_metrics(session, user.id)
        meditation = await _meditation_metrics(session, user.id, week_ago)
        journal = await _journal_metrics(session, user.id, week_ago)
        therapist = await _therapist_metrics(session, user.id)
        forecast = await _forecast_preview(session, user.id)

    # Time-based greeting using user's actual timezone hour
    hour = user_now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Append display name if set
    display_name = settings.display_name if settings else None
    if display_name:
        greeting = f"{greeting}, {display_name}"

    return {
        "greeting": greeting,
        "date": today.isoformat(),
        "mood": mood,
        "habits": habits,
        "goals": goals,
        "meditation": meditation,
        "journal": journal,
        "therapist": therapist,
        "forecast": forecast,
    }


async def _mood_metrics(session, user_id: str, since: datetime) -> dict:
    """Recent moods + streak."""
    MoodEntry = sys.modules["zugalife.models"].MoodEntry

    result = await session.execute(
        select(MoodEntry.emoji, MoodEntry.label, MoodEntry.created_at)
        .where(MoodEntry.user_id == user_id, MoodEntry.created_at >= since)
        .order_by(desc(MoodEntry.created_at))
        .limit(10)
    )
    entries = result.all()

    total_result = await session.execute(
        select(func.count())
        .select_from(MoodEntry)
        .where(MoodEntry.user_id == user_id)
    )
    total = total_result.scalar_one()

    return {
        "recent": [
            {"emoji": e.emoji, "label": e.label, "date": e.created_at.isoformat()}
            for e in entries
        ],
        "total": total,
        "has_data": total > 0,
    }


async def _forecast_preview(session, user_id: str) -> dict:
    """Lightweight forecast preview for dashboard — trend + tomorrow's forecast."""
    try:
        _engine = sys.modules["zugalife.forecasting.engine"]
        data = await _engine.compute_all(session, user_id, days=14)

        trend = data["trend"]
        forecast = data["forecast"]

        return {
            "has_data": data["total_entries"] >= 3,
            "trend_direction": trend["direction"],
            "trend_description": trend["description"],
            "forecast_label": forecast.get("forecast_label"),
            "forecast_description": forecast.get("description"),
        }
    except Exception:
        logger.warning("Forecast preview failed", exc_info=True)
        return {"has_data": False}


async def _habit_metrics(session, user_id: str, week_start: date, today: date) -> dict:
    """Weekly completion rate + streak."""
    _h = sys.modules["zugalife.habits.models"]
    HabitDefinition = _h.HabitDefinition
    HabitLog = _h.HabitLog

    # Active habits
    habits_result = await session.execute(
        select(HabitDefinition)
        .where(HabitDefinition.user_id == user_id, HabitDefinition.is_active == True)
    )
    habits = habits_result.scalars().all()
    if not habits:
        return {"has_data": False, "active_count": 0}

    # This week's completions
    days_in_week = (today - week_start).days + 1
    total_possible = len(habits) * days_in_week
    completed = 0
    habit_stats = []

    for h in habits:
        log_result = await session.execute(
            select(func.count())
            .select_from(HabitLog)
            .where(
                HabitLog.habit_id == h.id,
                HabitLog.user_id == user_id,
                HabitLog.log_date >= week_start,
                HabitLog.log_date <= today,
                HabitLog.completed == True,
            )
        )
        days = log_result.scalar_one()
        completed += days
        habit_stats.append({
            "name": h.name,
            "emoji": h.emoji,
            "completed": days,
            "total": days_in_week,
        })

    # Sort by completion rate descending for display
    habit_stats.sort(key=lambda x: x["completed"] / max(x["total"], 1), reverse=True)

    return {
        "has_data": True,
        "active_count": len(habits),
        "completed": completed,
        "total_possible": total_possible,
        "completion_rate": round(completed / max(total_possible, 1), 3),
        "top_habits": habit_stats[:5],
    }


async def _goal_metrics(session, user_id: str) -> dict:
    """Active goals + nearest deadline."""
    _g = sys.modules["zugalife.goals.models"]
    GoalDefinition = _g.GoalDefinition

    result = await session.execute(
        select(GoalDefinition)
        .where(GoalDefinition.user_id == user_id)
    )
    goals = result.scalars().all()
    if not goals:
        return {"has_data": False}

    active = [g for g in goals if not g.is_completed]
    completed = [g for g in goals if g.is_completed]

    # Nearest deadline among active goals
    nearest = None
    nearest_date = None
    for g in active:
        if g.deadline and (nearest_date is None or g.deadline < nearest_date):
            nearest_date = g.deadline
            nearest = {"title": g.title, "date": g.deadline.isoformat() if hasattr(g.deadline, 'isoformat') else str(g.deadline)}

    # Total milestone progress across active goals
    total_milestones = 0
    done_milestones = 0
    for g in active:
        ms = g.milestones or []
        total_milestones += len(ms)
        done_milestones += sum(1 for m in ms if m.is_completed)

    return {
        "has_data": True,
        "active": len(active),
        "completed": len(completed),
        "nearest_deadline": nearest,
        "milestones_done": done_milestones,
        "milestones_total": total_milestones,
    }


async def _meditation_metrics(session, user_id: str, since: datetime) -> dict:
    """Weekly meditation stats."""
    MeditationSession = sys.modules["zugalife.meditation.models"].MeditationSession

    result = await session.execute(
        select(
            func.count(),
            func.sum(MeditationSession.duration_minutes),
            func.avg(MeditationSession.duration_minutes),
        )
        .where(
            MeditationSession.user_id == user_id,
            MeditationSession.created_at >= since,
        )
    )
    row = result.one()
    count = row[0] or 0

    total_result = await session.execute(
        select(func.count())
        .select_from(MeditationSession)
        .where(MeditationSession.user_id == user_id)
    )
    total = total_result.scalar_one()

    if count == 0:
        return {"has_data": total > 0, "sessions_this_week": 0, "total_sessions": total}

    return {
        "has_data": True,
        "sessions_this_week": count,
        "total_minutes": int(row[1] or 0),
        "avg_minutes": int(row[2] or 0),
        "total_sessions": total,
    }


async def _journal_metrics(session, user_id: str, since: datetime) -> dict:
    """Weekly journal activity."""
    JournalEntry = sys.modules["zugalife.journal.models"].JournalEntry

    week_result = await session.execute(
        select(func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.user_id == user_id, JournalEntry.created_at >= since)
    )
    this_week = week_result.scalar_one()

    total_result = await session.execute(
        select(func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.user_id == user_id)
    )
    total = total_result.scalar_one()

    # Latest entry title for preview
    latest_result = await session.execute(
        select(JournalEntry.title, JournalEntry.created_at)
        .where(JournalEntry.user_id == user_id)
        .order_by(desc(JournalEntry.created_at))
        .limit(1)
    )
    latest = latest_result.first()

    return {
        "has_data": total > 0,
        "entries_this_week": this_week,
        "total": total,
        "latest_title": latest.title if latest else None,
        "latest_date": latest.created_at.isoformat() if latest else None,
    }


async def _therapist_metrics(session, user_id: str) -> dict:
    """Therapist session history."""
    TherapistSessionNote = sys.modules["zugalife.therapist.models"].TherapistSessionNote

    total_result = await session.execute(
        select(func.count())
        .select_from(TherapistSessionNote)
        .where(TherapistSessionNote.user_id == user_id)
    )
    total = total_result.scalar_one()

    if total == 0:
        return {"has_data": False, "total_sessions": 0}

    latest_result = await session.execute(
        select(TherapistSessionNote.themes, TherapistSessionNote.mood_snapshot, TherapistSessionNote.created_at)
        .where(TherapistSessionNote.user_id == user_id)
        .order_by(desc(TherapistSessionNote.created_at))
        .limit(1)
    )
    latest = latest_result.first()

    return {
        "has_data": True,
        "total_sessions": total,
        "last_date": latest.created_at.isoformat() if latest else None,
        "last_themes": latest.themes.split("\n")[0][:100] if latest and latest.themes else None,
        "last_mood": latest.mood_snapshot if latest else None,
    }
