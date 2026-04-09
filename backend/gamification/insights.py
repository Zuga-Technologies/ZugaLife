"""Contextual psychological insight cards — Deepstash-style micro-learning at optimal moments.

Psychology: Micro-learning at psychologically receptive moments has maximum retention.
After a meditation streak, a mood pattern detection, or a goal milestone — that's when
users are most open to absorbing a research-backed insight about what just happened.

The Spacing Effect (PNAS, 2019): distributed learning beats massed practice.
Short insights spread across the week beat a single long article.
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Insight card library — trigger condition + content
# ---------------------------------------------------------------------------

INSIGHT_CARDS: dict[str, dict] = {
    "meditation_streak_3": {
        "title": "Your brain is changing",
        "content": "After 3+ days of meditation, neuroimaging studies show increased gray matter density in the prefrontal cortex \u2014 the brain region responsible for self-regulation and attention.",
        "category": "neuroscience",
    },
    "meditation_streak_7": {
        "title": "Week of presence",
        "content": "7 consecutive days of meditation is where structural brain changes become measurable. The anterior cingulate cortex \u2014 your conflict monitoring center \u2014 is literally growing.",
        "category": "neuroscience",
    },
    "mood_improving_trend": {
        "title": "The upswing is real",
        "content": "Your mood trend is positive. Research shows that recognizing improvement reinforces the behaviors causing it \u2014 a virtuous cycle psychologists call the 'upward spiral' (Fredrickson, 2001).",
        "category": "psychology",
    },
    "habit_perfect_week": {
        "title": "The Progress Principle",
        "content": "You completed all habits this week. Teresa Amabile's research (12,000 diary entries) found that small wins like this are the single strongest predictor of positive inner work life.",
        "category": "psychology",
    },
    "goal_50pct": {
        "title": "Past the midpoint",
        "content": "You're over 50% through your milestones. The Goal Gradient Effect (Kivetz, 2006): effort accelerates as you approach completion. The closer you get, the faster you'll move.",
        "category": "psychology",
    },
    "streak_30": {
        "title": "Identity threshold",
        "content": "30 days. Phillippa Lally's UCL research found the average habit takes 66 days to become automatic \u2014 but you've passed the point where this stops being discipline and starts becoming identity.",
        "category": "research",
    },
    "streak_7": {
        "title": "The compound effect",
        "content": "A full week of showing up. James Clear: 'Every action is a vote for the type of person you want to become.' You've cast 7 votes this week.",
        "category": "psychology",
    },
    "journal_5_entries": {
        "title": "The writing effect",
        "content": "5+ journal entries this month. Pennebaker's 30 years of research: expressive writing reduces anxiety, improves immune function, and creates cognitive coherence from emotional chaos.",
        "category": "research",
    },
    "first_therapy_session": {
        "title": "Therapeutic alliance",
        "content": "Research on AI wellness bots (Wysa study, n=1,205): therapeutic bond scores reached 3.64 within 5 days \u2014 matching in-person CBT. What you just did has measurable psychological weight.",
        "category": "research",
    },
    "mood_monday_dip": {
        "title": "The Monday effect",
        "content": "Your mood tends to dip on Mondays. Psychologists call this the 'Blue Monday' effect \u2014 it's physiological, not a personal failing. A morning routine on Mondays has outsized impact.",
        "category": "pattern",
    },
    "breathwork_after_stress": {
        "title": "Your nervous system responded",
        "content": "Box breathing at 4-4-4-4 activates the vagus nerve within 60 seconds. The pre-B\u00F6tzinger complex in your brainstem dampens your locus coeruleus, reducing emotional reactivity. You just used Navy SEAL tactical breathing.",
        "category": "neuroscience",
    },
}


# ---------------------------------------------------------------------------
# Trigger evaluation
# ---------------------------------------------------------------------------

async def get_pending_insights(session, user_id: str) -> list[dict]:
    """Check trigger conditions and return insight cards that should be shown.

    Only returns insights not yet shown to this user. Max 2 per request.
    """
    _models = sys.modules["zugalife.gamification.models"]
    UserInsight = _models.UserInsight
    UserXP = _models.UserXP

    # Get already-shown insight keys
    shown_result = await session.execute(
        select(UserInsight.insight_key).where(UserInsight.user_id == user_id)
    )
    shown_keys = set(shown_result.scalars().all())

    # Gather user state for trigger evaluation
    xp_result = await session.execute(
        select(UserXP).where(UserXP.user_id == user_id)
    )
    user_xp = xp_result.scalar_one_or_none()
    streak = user_xp.current_streak_days if user_xp else 0

    pending = []

    # Streak-based triggers
    if streak >= 30 and "streak_30" not in shown_keys:
        pending.append(_card_with_key("streak_30"))
    elif streak >= 7 and "streak_7" not in shown_keys:
        pending.append(_card_with_key("streak_7"))

    # Meditation streak triggers
    MeditationSession = sys.modules.get("zugalife.meditation.models")
    if MeditationSession:
        MedSession = MeditationSession.MeditationSession
        week_ago = date.today() - timedelta(days=7)
        med_count_result = await session.execute(
            select(func.count()).where(
                MedSession.user_id == user_id,
                MedSession.status == "ready",
                func.date(MedSession.created_at) >= week_ago,
            )
        )
        med_count = med_count_result.scalar_one() or 0

        if med_count >= 7 and "meditation_streak_7" not in shown_keys:
            pending.append(_card_with_key("meditation_streak_7"))
        elif med_count >= 3 and "meditation_streak_3" not in shown_keys:
            pending.append(_card_with_key("meditation_streak_3"))

    # Journal entry count trigger
    JournalEntry = sys.modules.get("zugalife.journal.models")
    if JournalEntry:
        JEntry = JournalEntry.JournalEntry
        month_ago = datetime.now(timezone.utc) - timedelta(days=30)
        journal_count_result = await session.execute(
            select(func.count()).where(
                JEntry.user_id == user_id,
                JEntry.created_at >= month_ago,
            )
        )
        journal_count = journal_count_result.scalar_one() or 0
        if journal_count >= 5 and "journal_5_entries" not in shown_keys:
            pending.append(_card_with_key("journal_5_entries"))

    # Goal 50% trigger
    GoalDefinition = sys.modules["zugalife.goals.models"].GoalDefinition
    goals_result = await session.execute(
        select(GoalDefinition).where(
            GoalDefinition.user_id == user_id,
            GoalDefinition.is_completed == False,
        )
    )
    for goal in goals_result.scalars().all():
        total = len(goal.milestones)
        done = sum(1 for m in goal.milestones if m.is_completed)
        if total > 0 and done / total >= 0.5 and "goal_50pct" not in shown_keys:
            pending.append(_card_with_key("goal_50pct"))
            break

    # Mood trend trigger (check forecasting)
    try:
        _engine = sys.modules["zugalife.forecasting.engine"]
        entries = await _engine._fetch_mood_entries(session, user_id, 7)
        if len(entries) >= 3:
            trend = _engine.compute_trend(entries, 7)
            if trend.get("direction") == "improving" and "mood_improving_trend" not in shown_keys:
                pending.append(_card_with_key("mood_improving_trend"))
    except Exception:
        pass

    # Mark shown and return max 2
    result = pending[:2]
    for card in result:
        insight = UserInsight(user_id=user_id, insight_key=card["key"])
        session.add(insight)

    if result:
        await session.flush()

    return result


async def dismiss_insight(session, user_id: str, insight_key: str) -> bool:
    """Mark an insight as dismissed."""
    _models = sys.modules["zugalife.gamification.models"]
    UserInsight = _models.UserInsight

    result = await session.execute(
        select(UserInsight).where(
            UserInsight.user_id == user_id,
            UserInsight.insight_key == insight_key,
        )
    )
    insight = result.scalar_one_or_none()
    if insight:
        insight.dismissed_at = datetime.now(timezone.utc)
        await session.flush()
        return True
    return False


def _card_with_key(key: str) -> dict:
    """Return insight card dict with key included."""
    card = INSIGHT_CARDS.get(key, {})
    return {
        "key": key,
        "title": card.get("title", ""),
        "content": card.get("content", ""),
        "category": card.get("category", ""),
    }
