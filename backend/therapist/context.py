"""Therapist context assembly — builds a summary of the user's ZugaLife data.

SECURITY: Data flows ONE WAY into this module.
- This module READS from: mood_entries, journal_entries, habit_logs,
  habit_definitions, goal_definitions, meditation_sessions,
  therapist_session_notes.
- Therapist session notes are NEVER read by any other module.
- Output of this module goes ONLY to Venice (via task="therapist").
"""

import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func, select

from core.database.session import get_session


async def build_user_context(user_id: str) -> str:
    """Assemble a text summary of the user's recent ZugaLife data.

    This context is prepended to the therapist's system prompt so it
    can make grounded, data-informed observations.
    """
    sections = []

    async with get_session() as session:
        mood_summary = await _mood_summary(session, user_id)
        if mood_summary:
            sections.append(mood_summary)

        habit_summary = await _habit_summary(session, user_id)
        if habit_summary:
            sections.append(habit_summary)

        goal_summary = await _goal_summary(session, user_id)
        if goal_summary:
            sections.append(goal_summary)

        journal_summary = await _journal_summary(session, user_id)
        if journal_summary:
            sections.append(journal_summary)

        meditation_summary = await _meditation_summary(session, user_id)
        if meditation_summary:
            sections.append(meditation_summary)

    # Forecasting context runs its own session (separate module)
    try:
        _forecast_ctx = sys.modules.get("zugalife.forecasting.context")
        if _forecast_ctx:
            forecast_summary = await _forecast_ctx.build_forecast_context(user_id)
            if forecast_summary:
                sections.append(forecast_summary)
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Forecast context failed, skipping", exc_info=True)

    async with get_session() as session:
        session_notes = await _recent_session_notes(session, user_id)
        if session_notes:
            sections.append(session_notes)

    if not sections:
        return "I don't have much data on you yet — this might be a fresh start."

    return "\n\n".join(sections)


async def get_last_session_reference(user_id: str) -> str | None:
    """Get a brief reference to the last therapist session for greeting."""
    _models = sys.modules["zugalife.therapist.models"]
    TherapistSessionNote = _models.TherapistSessionNote

    async with get_session() as session:
        result = await session.execute(
            select(TherapistSessionNote)
            .where(TherapistSessionNote.user_id == user_id)
            .order_by(desc(TherapistSessionNote.created_at))
            .limit(1)
        )
        note = result.scalar_one_or_none()

    if not note:
        return None

    return f"Last time we talked about: {note.themes}"


async def count_today_sessions(user_id: str) -> int:
    """Count therapist sessions created today."""
    _models = sys.modules["zugalife.therapist.models"]
    TherapistSessionNote = _models.TherapistSessionNote

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )

    async with get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(TherapistSessionNote)
            .where(
                TherapistSessionNote.user_id == user_id,
                TherapistSessionNote.created_at >= today_start,
            )
        )
        return result.scalar_one()


async def is_first_session(user_id: str) -> bool:
    """Check if user has ever had a therapist session."""
    _models = sys.modules["zugalife.therapist.models"]
    TherapistSessionNote = _models.TherapistSessionNote

    async with get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(TherapistSessionNote)
            .where(TherapistSessionNote.user_id == user_id)
        )
        return result.scalar_one() == 0


# --- Private helpers ---


async def _mood_summary(session, user_id: str) -> str | None:
    """Summarize recent mood entries."""
    MoodEntry = sys.modules["zugalife.models"].MoodEntry

    since = datetime.now(timezone.utc) - timedelta(days=7)
    result = await session.execute(
        select(MoodEntry.emoji, MoodEntry.label, MoodEntry.note)
        .where(MoodEntry.user_id == user_id, MoodEntry.created_at >= since)
        .order_by(desc(MoodEntry.created_at))
        .limit(10)
    )
    entries = result.all()
    if not entries:
        return None

    lines = [f"  {e.emoji} {e.label}" + (f" — \"{e.note[:80]}\"" if e.note else "") for e in entries]
    return "Recent moods (last 7 days):\n" + "\n".join(lines)


async def _habit_summary(session, user_id: str) -> str | None:
    """Summarize habit performance this week."""
    _h = sys.modules["zugalife.habits.models"]
    HabitDefinition = _h.HabitDefinition
    HabitLog = _h.HabitLog

    since = date.today() - timedelta(days=6)

    habits_result = await session.execute(
        select(HabitDefinition)
        .where(HabitDefinition.user_id == user_id, HabitDefinition.is_active == True)
    )
    habits = habits_result.scalars().all()
    if not habits:
        return None

    preset_habits = [h for h in habits if h.is_preset]
    custom_habits = [h for h in habits if not h.is_preset]

    lines = []
    total_completions = 0
    for h in habits:
        log_result = await session.execute(
            select(func.count())
            .select_from(HabitLog)
            .where(
                HabitLog.habit_id == h.id,
                HabitLog.user_id == user_id,
                HabitLog.log_date >= since,
                HabitLog.completed == True,
            )
        )
        days = log_result.scalar_one()
        total_completions += days
        label = h.name if not h.is_preset else f"{h.name} (default)"
        lines.append(f"  {label}: {days}/7 days")

    # Check if user has EVER logged any habits (not just this week)
    if total_completions == 0:
        any_logs = await session.execute(
            select(func.count())
            .select_from(HabitLog)
            .where(HabitLog.user_id == user_id, HabitLog.completed == True)
        )
        if any_logs.scalar_one() == 0:
            # Distinguish between system defaults and user-created habits
            parts = []
            if preset_habits:
                parts.append(
                    f"The app provided {len(preset_habits)} default starter habits "
                    f"({', '.join(h.name for h in preset_habits)}). "
                    "These are system defaults, NOT habits the user personally chose. "
                    "Do not praise them for 'choosing' these habits."
                )
            if custom_habits:
                parts.append(
                    f"The user also CREATED {len(custom_habits)} custom habit(s): "
                    f"{', '.join(h.name for h in custom_habits)}. "
                    "This IS a meaningful, intentional step — acknowledge it warmly. "
                    "Ask what motivated them to add these specific habits."
                )
            if not custom_habits:
                parts.append(
                    "The user hasn't started tracking any habits yet. "
                    "If relevant, you could gently explore whether any of the "
                    "default habits resonate or if they'd like to add their own."
                )
            return "Habits:\n" + "\n".join(parts)

    return "Habit performance (last 7 days):\n" + "\n".join(lines)


async def _goal_summary(session, user_id: str) -> str | None:
    """Summarize active goals."""
    _g = sys.modules["zugalife.goals.models"]
    GoalDefinition = _g.GoalDefinition
    GoalMilestone = _g.GoalMilestone

    result = await session.execute(
        select(GoalDefinition)
        .where(GoalDefinition.user_id == user_id, GoalDefinition.is_completed == False)
        .order_by(GoalDefinition.sort_order)
    )
    goals = result.scalars().all()
    if not goals:
        return None

    lines = []
    for g in goals:
        ms = g.milestones or []
        done = sum(1 for m in ms if m.is_completed)
        total = len(ms)
        progress = f" ({done}/{total} milestones)" if total > 0 else ""
        deadline = f" [deadline: {g.deadline}]" if g.deadline else ""
        lines.append(f"  {g.title}{progress}{deadline}")

    return "Active goals:\n" + "\n".join(lines)


async def _journal_summary(session, user_id: str) -> str | None:
    """Summarize recent journal entry themes."""
    JournalEntry = sys.modules["zugalife.journal.models"].JournalEntry

    since = datetime.now(timezone.utc) - timedelta(days=14)
    result = await session.execute(
        select(JournalEntry.title, JournalEntry.mood_emoji, JournalEntry.mood_label)
        .where(JournalEntry.user_id == user_id, JournalEntry.created_at >= since)
        .order_by(desc(JournalEntry.created_at))
        .limit(5)
    )
    entries = result.all()
    if not entries:
        return None

    lines = []
    for e in entries:
        mood = f" [{e.mood_emoji} {e.mood_label}]" if e.mood_emoji else ""
        title = e.title or "(untitled)"
        lines.append(f"  {title}{mood}")

    return "Recent journal entries (last 14 days):\n" + "\n".join(lines)


async def _meditation_summary(session, user_id: str) -> str | None:
    """Summarize recent meditation activity."""
    MeditationSession = sys.modules["zugalife.meditation.models"].MeditationSession

    since = datetime.now(timezone.utc) - timedelta(days=7)
    result = await session.execute(
        select(
            func.count(),
            func.avg(MeditationSession.duration_minutes),
        )
        .where(
            MeditationSession.user_id == user_id,
            MeditationSession.created_at >= since,
        )
    )
    row = result.one()
    count = row[0]
    if count == 0:
        # Check if user has EVER meditated
        any_sessions = await session.execute(
            select(func.count())
            .select_from(MeditationSession)
            .where(MeditationSession.user_id == user_id)
        )
        if any_sessions.scalar_one() == 0:
            return None  # Never meditated — don't mention it
        return "Meditation: No sessions in the last 7 days."

    avg_duration = int(row[1] or 0)
    return f"Meditation: {count} sessions in the last 7 days (avg ~{avg_duration} min)."


async def _recent_session_notes(session, user_id: str) -> str | None:
    """Get last 3 therapist session notes for continuity."""
    _models = sys.modules["zugalife.therapist.models"]
    TherapistSessionNote = _models.TherapistSessionNote

    result = await session.execute(
        select(TherapistSessionNote)
        .where(TherapistSessionNote.user_id == user_id)
        .order_by(desc(TherapistSessionNote.created_at))
        .limit(3)
    )
    notes = result.scalars().all()
    if not notes:
        return None

    lines = []
    for note in reversed(notes):  # oldest first
        date_str = note.created_at.strftime("%b %d")
        lines.append(
            f"  [{date_str}] Themes: {note.themes}"
            + (f" | Patterns: {note.patterns}" if note.patterns else "")
            + (f" | Follow-up: {note.follow_up}" if note.follow_up else "")
        )

    return "Previous session notes:\n" + "\n".join(lines)
