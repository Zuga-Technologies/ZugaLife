"""ZugaLife habit tracking endpoints."""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.exc import IntegrityError

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.habits.models"]
_schemas = sys.modules["zugalife.habits.schemas"]
_prompts = sys.modules["zugalife.habits.prompts"]

# Also need journal model for AI insights (mood source)
_journal_models = sys.modules["zugalife.journal.models"]

def _get_gam_engine():
    """Lazy lookup — gamification loads after habits in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

logger = logging.getLogger(__name__)

# Pull into globals for FastAPI annotation resolution
HabitDefinition = _models.HabitDefinition
HabitLog = _models.HabitLog
HabitInsight = _models.HabitInsight
JournalEntry = _journal_models.JournalEntry

HabitCreateRequest = _schemas.HabitCreateRequest
HabitUpdateRequest = _schemas.HabitUpdateRequest
HabitLogRequest = _schemas.HabitLogRequest
HabitDefinitionResponse = _schemas.HabitDefinitionResponse
HabitLogResponse = _schemas.HabitLogResponse
DailyCheckInResponse = _schemas.DailyCheckInResponse
HabitCheckInItem = _schemas.HabitCheckInItem
AllStreaksResponse = _schemas.AllStreaksResponse
HabitStreakInfo = _schemas.HabitStreakInfo
HabitHistoryResponse = _schemas.HabitHistoryResponse
DayHistory = _schemas.DayHistory
HabitInsightResponse = _schemas.HabitInsightResponse
HabitInsightListResponse = _schemas.HabitInsightListResponse
WeeklyTargetItem = _schemas.WeeklyTargetItem
WeeklyTargetsResponse = _schemas.WeeklyTargetsResponse

INSIGHT_COOLDOWN_DAYS = _prompts.INSIGHT_COOLDOWN_DAYS

router = APIRouter(prefix="/api/life/habits", tags=["life-habits"])

# 8 preset habits auto-seeded on first access
_PRESETS = [
    {"name": "Sleep", "emoji": "\U0001f634", "unit": "hours", "default_target": 8, "sort_order": 0},
    {"name": "Exercise", "emoji": "\U0001f3cb", "unit": "minutes", "default_target": 30, "sort_order": 1},
    {"name": "Water", "emoji": "\U0001f4a7", "unit": "glasses", "default_target": 8, "sort_order": 2},
    {"name": "Meditation", "emoji": "\U0001f9d8", "unit": "minutes", "default_target": 10, "sort_order": 3},
    {"name": "Reading", "emoji": "\U0001f4d6", "unit": "minutes", "default_target": 20, "sort_order": 4},
    {"name": "Healthy Eating", "emoji": "\U0001f957", "unit": None, "default_target": None, "sort_order": 5},
    {"name": "No Screens Before Bed", "emoji": "\U0001f4f5", "unit": None, "default_target": None, "sort_order": 6},
    {"name": "Gratitude", "emoji": "\U0001f64f", "unit": None, "default_target": None, "sort_order": 7},
]


async def _ensure_presets(session, user_id: str) -> None:
    """Auto-seed preset habits for a user if they have none yet.

    Race-safe: multiple concurrent requests may all see count==0 and try
    to seed. We catch IntegrityError (UNIQUE on user_id+name) and silently
    skip — the first request wins, others are no-ops.
    """
    count_result = await session.execute(
        select(func.count())
        .select_from(HabitDefinition)
        .where(HabitDefinition.user_id == user_id)
    )
    if count_result.scalar_one() > 0:
        return

    for preset in _PRESETS:
        habit = HabitDefinition(
            user_id=user_id,
            name=preset["name"],
            emoji=preset["emoji"],
            unit=preset["unit"],
            default_target=preset["default_target"],
            is_preset=True,
            is_active=True,
            sort_order=preset["sort_order"],
        )
        session.add(habit)

    try:
        await session.flush()
    except IntegrityError:
        # Another concurrent request already seeded — that's fine
        await session.rollback()


# --- Habit Definition CRUD ---


@router.get("", response_model=list[HabitDefinitionResponse])
async def list_habits(
    user: CurrentUser = Depends(get_current_user),
):
    """List all habit definitions. Auto-seeds presets on first call."""
    async with get_session() as session:
        await _ensure_presets(session, user.id)

        result = await session.execute(
            select(HabitDefinition)
            .where(HabitDefinition.user_id == user.id)
            .order_by(HabitDefinition.sort_order, HabitDefinition.id)
        )
        habits = result.scalars().all()

    return [HabitDefinitionResponse.model_validate(h) for h in habits]


@router.post("", response_model=HabitDefinitionResponse, status_code=201)
async def create_habit(
    body: HabitCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a custom habit."""
    async with get_session() as session:
        # Check for duplicate name
        existing = await session.execute(
            select(func.count())
            .select_from(HabitDefinition)
            .where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.name == body.name,
            )
        )
        if existing.scalar_one() > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Habit '{body.name}' already exists",
            )

        # Get max sort_order for placement at end
        max_order = await session.execute(
            select(func.max(HabitDefinition.sort_order))
            .where(HabitDefinition.user_id == user.id)
        )
        next_order = (max_order.scalar_one() or 0) + 1

        habit = HabitDefinition(
            user_id=user.id,
            name=body.name,
            emoji=body.emoji,
            unit=body.unit or None,
            default_target=body.default_target,
            is_preset=False,
            is_active=True,
            sort_order=next_order,
        )
        session.add(habit)
        await session.flush()
        await session.refresh(habit)

    return HabitDefinitionResponse.model_validate(habit)


@router.get("/weekly", response_model=WeeklyTargetsResponse)
async def get_weekly_targets(
    user: CurrentUser = Depends(get_current_user),
):
    """Get weekly target progress for all habits that have a target set."""
    today = date.today()
    # ISO week: Monday=0. Get this week's Monday.
    week_start = today - timedelta(days=today.weekday())

    async with get_session() as session:
        # Habits with a weekly_target set
        result = await session.execute(
            select(HabitDefinition)
            .where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.is_active == True,  # noqa: E712
                HabitDefinition.weekly_target.isnot(None),
            )
            .order_by(HabitDefinition.sort_order)
        )
        habits = result.scalars().all()

        if not habits:
            return WeeklyTargetsResponse(habits=[], week_start=week_start)

        # Count completed logs this week per habit
        habit_ids = [h.id for h in habits]
        logs_result = await session.execute(
            select(HabitLog.habit_id, func.count())
            .where(
                HabitLog.user_id == user.id,
                HabitLog.habit_id.in_(habit_ids),
                HabitLog.log_date >= week_start,
                HabitLog.log_date <= today,
                HabitLog.completed == True,  # noqa: E712
            )
            .group_by(HabitLog.habit_id)
        )
        counts = dict(logs_result.all())

        items = []
        for habit in habits:
            count = counts.get(habit.id, 0)
            target = habit.weekly_target
            pct = min(round(count / target * 100, 1), 100.0)
            items.append(WeeklyTargetItem(
                habit_id=habit.id,
                habit_name=habit.name,
                habit_emoji=habit.emoji,
                weekly_target=target,
                this_week_count=count,
                progress_pct=pct,
            ))

    return WeeklyTargetsResponse(habits=items, week_start=week_start)


@router.patch("/{habit_id}", response_model=HabitDefinitionResponse)
async def update_habit(
    habit_id: int,
    body: HabitUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update a habit definition (rename, toggle active, reorder)."""
    async with get_session() as session:
        result = await session.execute(
            select(HabitDefinition).where(HabitDefinition.id == habit_id)
        )
        habit = result.scalar_one_or_none()

        if not habit or habit.user_id != user.id:
            raise HTTPException(status_code=404, detail="Habit not found")

        # Check name uniqueness if renaming
        if body.name is not None and body.name != habit.name:
            dup = await session.execute(
                select(func.count())
                .select_from(HabitDefinition)
                .where(
                    HabitDefinition.user_id == user.id,
                    HabitDefinition.name == body.name,
                    HabitDefinition.id != habit_id,
                )
            )
            if dup.scalar_one() > 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"Habit '{body.name}' already exists",
                )
            habit.name = body.name

        if body.emoji is not None:
            habit.emoji = body.emoji
        if body.is_active is not None:
            habit.is_active = body.is_active
        if body.sort_order is not None:
            habit.sort_order = body.sort_order

        # weekly_target: distinguish "not sent" vs "sent as null" (to clear)
        if "weekly_target" in body.model_fields_set:
            habit.weekly_target = body.weekly_target

        await session.flush()
        await session.refresh(habit)

    return HabitDefinitionResponse.model_validate(habit)


@router.delete("/{habit_id}", status_code=204)
async def delete_habit(
    habit_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a custom habit. Presets can only be deactivated, not deleted."""
    async with get_session() as session:
        result = await session.execute(
            select(HabitDefinition).where(HabitDefinition.id == habit_id)
        )
        habit = result.scalar_one_or_none()

        if not habit or habit.user_id != user.id:
            raise HTTPException(status_code=404, detail="Habit not found")

        if habit.is_preset:
            raise HTTPException(
                status_code=400,
                detail="Preset habits cannot be deleted — deactivate them instead",
            )

        await session.delete(habit)


# --- Habit Logging ---


@router.post("/log", response_model=HabitLogResponse, status_code=201)
async def log_habit(
    body: HabitLogRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Log or update a habit for a date. Upserts — same habit+date updates the existing log."""
    log_date = body.log_date or date.today()

    async with get_session() as session:
        # Verify habit exists and belongs to user
        habit_result = await session.execute(
            select(HabitDefinition).where(HabitDefinition.id == body.habit_id)
        )
        habit = habit_result.scalar_one_or_none()
        if not habit or habit.user_id != user.id:
            raise HTTPException(status_code=404, detail="Habit not found")

        # Upsert: check for existing log
        existing = await session.execute(
            select(HabitLog).where(
                HabitLog.user_id == user.id,
                HabitLog.habit_id == body.habit_id,
                HabitLog.log_date == log_date,
            )
        )
        log = existing.scalar_one_or_none()
        was_already_completed = log.completed if log else False

        if log:
            # Update existing
            log.completed = body.completed
            log.amount = body.amount
        else:
            # Create new
            log = HabitLog(
                user_id=user.id,
                habit_id=body.habit_id,
                log_date=log_date,
                completed=body.completed,
                amount=body.amount,
            )
            session.add(log)

        try:
            await session.flush()
        except IntegrityError:
            # Race condition: concurrent request created the row between
            # our SELECT and INSERT. Rollback and retry as update.
            await session.rollback()
            existing = await session.execute(
                select(HabitLog).where(
                    HabitLog.user_id == user.id,
                    HabitLog.habit_id == body.habit_id,
                    HabitLog.log_date == log_date,
                )
            )
            log = existing.scalar_one()
            log.completed = body.completed
            log.amount = body.amount
            await session.flush()

        await session.refresh(log)

        # Only award XP once per habit per day — check XP transaction log
        gam = _get_gam_engine()
        already_awarded = False
        if gam and body.completed:
            _gam_models = sys.modules.get("zugalife.gamification.models")
            if _gam_models:
                xp_check = await session.execute(
                    select(_gam_models.XPTransaction.id).where(
                        _gam_models.XPTransaction.user_id == user.id,
                        _gam_models.XPTransaction.source == "habit_check",
                        _gam_models.XPTransaction.description == f"Completed {habit.name}",
                        func.date(_gam_models.XPTransaction.created_at) == log_date,
                    ).limit(1)
                )
                already_awarded = xp_check.scalar_one_or_none() is not None
        if gam and body.completed and not already_awarded:
            try:
                await gam.award_xp(
                    session, user_id=user.id,
                    source="habit_check",
                    description=f"Completed {habit.name}",
                )
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

    return HabitLogResponse.model_validate(log)


@router.delete("/log/{habit_id}/{log_date}", status_code=204)
async def uncheck_habit(
    habit_id: int,
    log_date: date,
    user: CurrentUser = Depends(get_current_user),
):
    """Remove a habit log for a specific date (uncheck)."""
    async with get_session() as session:
        result = await session.execute(
            select(HabitLog).where(
                HabitLog.user_id == user.id,
                HabitLog.habit_id == habit_id,
                HabitLog.log_date == log_date,
            )
        )
        log = result.scalar_one_or_none()
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")

        await session.delete(log)


# --- Reset ---


@router.delete("/reset/today", status_code=200)
async def reset_today(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all habit logs for today — uncheck everything."""
    async with get_session() as session:
        result = await session.execute(
            delete(HabitLog)
            .where(
                HabitLog.user_id == user.id,
                HabitLog.log_date == date.today(),
            )
            .returning(HabitLog.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/history", status_code=200)
async def reset_all_history(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete ALL habit logs for this user. Streaks reset to zero."""
    async with get_session() as session:
        result = await session.execute(
            delete(HabitLog)
            .where(HabitLog.user_id == user.id)
            .returning(HabitLog.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/{habit_id}", status_code=200)
async def reset_single_habit(
    habit_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all logs for a single habit. Its streak resets to zero."""
    async with get_session() as session:
        # Verify ownership
        habit = (await session.execute(
            select(HabitDefinition).where(
                HabitDefinition.id == habit_id,
                HabitDefinition.user_id == user.id,
            )
        )).scalar_one_or_none()
        if not habit:
            raise HTTPException(404, "Habit not found")

        result = await session.execute(
            delete(HabitLog)
            .where(
                HabitLog.user_id == user.id,
                HabitLog.habit_id == habit_id,
            )
            .returning(HabitLog.id)
        )
        count = len(result.all())
    return {"deleted": count, "habit": habit.name}


# --- Check-in & History ---


@router.get("/checkin", response_model=DailyCheckInResponse)
async def get_checkin(
    check_date: date | None = Query(None, alias="date"),
    user: CurrentUser = Depends(get_current_user),
):
    """Get today's (or a specific date's) check-in view — all habits with their log status."""
    target_date = check_date or date.today()

    async with get_session() as session:
        await _ensure_presets(session, user.id)

        # Get all active habits
        habits_result = await session.execute(
            select(HabitDefinition)
            .where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.is_active == True,  # noqa: E712
            )
            .order_by(HabitDefinition.sort_order, HabitDefinition.id)
        )
        habits = habits_result.scalars().all()

        # Get logs for this date
        logs_result = await session.execute(
            select(HabitLog).where(
                HabitLog.user_id == user.id,
                HabitLog.log_date == target_date,
            )
        )
        logs = {log.habit_id: log for log in logs_result.scalars().all()}

        items = []
        completed = 0
        for habit in habits:
            log = logs.get(habit.id)
            if log and log.completed:
                completed += 1
            items.append(HabitCheckInItem(
                habit=HabitDefinitionResponse.model_validate(habit),
                logged=log is not None and log.completed,
                amount=log.amount if log else None,
                log_id=log.id if log else None,
            ))

    return DailyCheckInResponse(
        date=target_date,
        habits=items,
        completed_count=completed,
        total_count=len(habits),
    )


@router.get("/history", response_model=HabitHistoryResponse)
async def get_history(
    days: int = Query(7, ge=1, le=90),
    user: CurrentUser = Depends(get_current_user),
):
    """Get day-by-day habit history with completion rates."""
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    async with get_session() as session:
        # Count active habits (for completion rate denominator)
        active_count_result = await session.execute(
            select(func.count())
            .select_from(HabitDefinition)
            .where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.is_active == True,  # noqa: E712
            )
        )
        total_active = active_count_result.scalar_one()

        if total_active == 0:
            return HabitHistoryResponse(days=[], period_days=days)

        # Get all logs in the period
        logs_result = await session.execute(
            select(HabitLog)
            .where(
                HabitLog.user_id == user.id,
                HabitLog.log_date >= start_date,
                HabitLog.log_date <= today,
                HabitLog.completed == True,  # noqa: E712
            )
        )
        logs = logs_result.scalars().all()

        # Get habit emoji lookup
        habits_result = await session.execute(
            select(HabitDefinition.id, HabitDefinition.emoji)
            .where(HabitDefinition.user_id == user.id)
        )
        emoji_map = {row[0]: row[1] for row in habits_result.all()}

        # Group logs by date
        logs_by_date: dict[date, list] = {}
        for log in logs:
            logs_by_date.setdefault(log.log_date, []).append(log)

        # Build day-by-day
        day_list = []
        d = today
        while d >= start_date:
            day_logs = logs_by_date.get(d, [])
            done_count = len(day_logs)
            emojis = [emoji_map.get(log.habit_id, "") for log in day_logs]
            rate = round(done_count / total_active, 2) if total_active else 0.0
            day_list.append(DayHistory(
                date=d,
                completed_count=done_count,
                total_active=total_active,
                completion_rate=rate,
                habits_done=emojis,
            ))
            d -= timedelta(days=1)

    return HabitHistoryResponse(days=day_list, period_days=days)


# --- Streaks ---


@router.get("/streaks", response_model=AllStreaksResponse)
async def get_streaks(
    user: CurrentUser = Depends(get_current_user),
):
    """Get current and longest streak per habit + overall."""
    async with get_session() as session:
        await _ensure_presets(session, user.id)

        # Get user's timezone-aware today
        _helpers = sys.modules["zugalife.settings_helpers"]
        user_today = await _helpers.get_user_today(session, user.id)

        # Get active habits
        habits_result = await session.execute(
            select(HabitDefinition)
            .where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.is_active == True,  # noqa: E712
            )
            .order_by(HabitDefinition.sort_order)
        )
        habits = habits_result.scalars().all()

        # Get all completed logs
        logs_result = await session.execute(
            select(HabitLog)
            .where(
                HabitLog.user_id == user.id,
                HabitLog.completed == True,  # noqa: E712
            )
            .order_by(desc(HabitLog.log_date))
        )
        all_logs = logs_result.scalars().all()

        # Group logs by habit_id
        active_ids = {h.id for h in habits}
        logs_by_habit: dict[int, list[date]] = {}
        active_dates: set[date] = set()
        for log in all_logs:
            logs_by_habit.setdefault(log.habit_id, []).append(log.log_date)
            if log.habit_id in active_ids:
                active_dates.add(log.log_date)

        # Calculate per-habit streaks (active habits only)
        streak_infos = []
        for habit in habits:
            dates = sorted(set(logs_by_habit.get(habit.id, [])), reverse=True)
            current, longest = _calculate_streaks(dates, today=user_today)
            streak_infos.append(HabitStreakInfo(
                habit_id=habit.id,
                habit_name=habit.name,
                habit_emoji=habit.emoji,
                current_streak=current,
                longest_streak=longest,
            ))

        # Overall streak: consecutive days with at least 1 ACTIVE habit logged
        overall_dates = sorted(active_dates, reverse=True)
        overall_current, overall_longest = _calculate_streaks(overall_dates, today=user_today)

    return AllStreaksResponse(
        habits=streak_infos,
        overall_current=overall_current,
        overall_longest=overall_longest,
    )


def _calculate_streaks(dates: list[date], today: date | None = None) -> tuple[int, int]:
    """Calculate current and longest streak from a sorted (desc) list of unique dates.

    Accepts an optional `today` param for timezone-aware streak calculation.
    Falls back to date.today() if not provided (server time).
    """
    if not dates:
        return 0, 0

    if today is None:
        today = date.today()

    # Current streak: must include today (strict — no grace period)
    if dates[0] != today:
        current = 0
    else:
        current = 1
        for i in range(1, len(dates)):
            if dates[i - 1] - dates[i] == timedelta(days=1):
                current += 1
            else:
                break

    # Longest streak: scan all dates
    longest = 1 if dates else 0
    run = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return current, longest


# --- AI Insights ---


@router.post("/insight", response_model=HabitInsightResponse, status_code=201)
async def generate_insight(
    user: CurrentUser = Depends(get_current_user),
):
    """Generate an AI weekly insight correlating habits with moods. 7-day cooldown."""
    try:
        from core.ai.gateway import BudgetExhaustedError, PromptBlockedError, ai_call
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="AI insights not available in standalone mode",
        )

    async with get_session() as session:
        # Check cooldown
        cutoff = date.today() - timedelta(days=INSIGHT_COOLDOWN_DAYS)
        recent_result = await session.execute(
            select(func.count())
            .select_from(HabitInsight)
            .where(
                HabitInsight.user_id == user.id,
                HabitInsight.week_start >= cutoff,
            )
        )
        if recent_result.scalar_one() > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Insight cooldown active. You can generate one insight per {INSIGHT_COOLDOWN_DAYS} days.",
            )

        # Gather 7 days of habit data
        week_start = date.today() - timedelta(days=6)
        habit_days = await _gather_habit_data(session, user.id, week_start)
        habit_text = _prompts.format_habit_data(habit_days)

        # Gather 7 days of mood data
        mood_entries = await _gather_mood_data(session, user.id, week_start)
        mood_text = _prompts.format_mood_data(mood_entries)

        # Get previous insights for anti-repetition
        prev_result = await session.execute(
            select(HabitInsight.content)
            .where(HabitInsight.user_id == user.id)
            .order_by(desc(HabitInsight.created_at))
            .limit(3)
        )
        previous = [row[0] for row in prev_result.all()]

        prompt = _prompts.build_insight_prompt(
            habit_data=habit_text,
            mood_data=mood_text,
            previous_insights=previous if previous else None,
        )

        from core.ai.gateway import CreditBlockedError
        try:
            ai_response = await ai_call(
                prompt, task="chat", max_tokens=2048,
                user_id=user.id, user_email=user.email,
            )
        except (BudgetExhaustedError, CreditBlockedError):
            raise HTTPException(
                status_code=402,
                detail="Daily AI budget exhausted",
            )
        except PromptBlockedError:
            raise HTTPException(
                status_code=400,
                detail="Content blocked by security filter",
            )

        insight = HabitInsight(
            user_id=user.id,
            content=ai_response.content,
            model_used=ai_response.model,
            cost=ai_response.cost,
            week_start=week_start,
        )
        session.add(insight)
        await session.flush()
        await session.refresh(insight)

    return HabitInsightResponse.model_validate(insight)


@router.get("/insights", response_model=HabitInsightListResponse)
async def list_insights(
    limit: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(get_current_user),
):
    """List past AI habit insights."""
    async with get_session() as session:
        count_result = await session.execute(
            select(func.count())
            .select_from(HabitInsight)
            .where(HabitInsight.user_id == user.id)
        )
        total = count_result.scalar_one()

        result = await session.execute(
            select(HabitInsight)
            .where(HabitInsight.user_id == user.id)
            .order_by(desc(HabitInsight.created_at))
            .limit(limit)
        )
        insights = result.scalars().all()

    return HabitInsightListResponse(
        insights=[HabitInsightResponse.model_validate(i) for i in insights],
        total=total,
    )


# --- Private helpers ---


async def _gather_habit_data(
    session, user_id: str, since: date,
) -> list[dict]:
    """Gather habit data for the prompt, organized by day."""
    # Get habit definitions for emoji/name lookup
    habits_result = await session.execute(
        select(HabitDefinition)
        .where(HabitDefinition.user_id == user_id)
    )
    habit_map = {h.id: h for h in habits_result.scalars().all()}

    # Get logs in the period
    logs_result = await session.execute(
        select(HabitLog)
        .where(
            HabitLog.user_id == user_id,
            HabitLog.log_date >= since,
            HabitLog.completed == True,  # noqa: E712
        )
        .order_by(HabitLog.log_date)
    )
    logs = logs_result.scalars().all()

    # Group by date
    logs_by_date: dict[date, list] = {}
    for log in logs:
        logs_by_date.setdefault(log.log_date, []).append(log)

    days = []
    d = since
    today = date.today()
    while d <= today:
        day_habits = []
        for log in logs_by_date.get(d, []):
            habit = habit_map.get(log.habit_id)
            if habit:
                day_habits.append({
                    "name": habit.name,
                    "emoji": habit.emoji,
                    "completed": log.completed,
                    "amount": log.amount,
                    "unit": habit.unit,
                })
        days.append({"date": d.isoformat(), "habits": day_habits})
        d += timedelta(days=1)

    return days


async def _gather_mood_data(
    session, user_id: str, since: date,
) -> list[dict]:
    """Gather mood data from journal entries for the insight prompt."""
    since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    result = await session.execute(
        select(JournalEntry)
        .where(
            JournalEntry.user_id == user_id,
            JournalEntry.created_at >= since_dt,
            JournalEntry.mood_emoji.isnot(None),
        )
        .order_by(JournalEntry.created_at)
    )
    entries = result.scalars().all()

    return [
        {
            "date": entry.created_at.strftime("%Y-%m-%d"),
            "emoji": entry.mood_emoji,
            "label": entry.mood_label,
            "note": entry.content[:200],
        }
        for entry in entries
    ]
