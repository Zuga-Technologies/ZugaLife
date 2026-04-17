"""Weekly narrative synthesis — AI-generated summary of mood, habits, goals, and identity.

The #1 gap in mood tracking research: users get data but no interpretation.
This module generates a 3-4 paragraph narrative connecting mood trends, habit
correlations, goal progress, and identity reinforcement into a cohesive story.

Cached: one AI call per user per week (stored in WeeklyNarrative table).
"""

import logging
import sys
from datetime import date, timedelta

from sqlalchemy import desc, select

logger = logging.getLogger(__name__)


async def generate_weekly_narrative(
    session, user_id: str, user_email: str | None = None,
) -> dict:
    """Generate or retrieve the cached weekly narrative for a user.

    Returns: {narrative: str, highlights: list[str], generated_at: str, cached: bool}
    """
    _models = sys.modules.get("zugalife.forecasting.models")
    if not _models:
        return {"narrative": None, "highlights": [], "error": "Models not loaded"}

    WeeklyNarrative = _models.WeeklyNarrative

    # Determine current week (Monday-based)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    # Check cache — use first() + created_at desc in case a race produced duplicates
    # (no unique index on (user_id, week_start), so concurrent requests can double-insert)
    cached = await session.execute(
        select(WeeklyNarrative)
        .where(
            WeeklyNarrative.user_id == user_id,
            WeeklyNarrative.week_start == week_start,
        )
        .order_by(desc(WeeklyNarrative.created_at))
        .limit(1)
    )
    existing = cached.scalars().first()
    if existing:
        return {
            "narrative": existing.narrative,
            "highlights": _parse_highlights(existing.highlights),
            "generated_at": existing.created_at.isoformat() if existing.created_at else None,
            "cached": True,
            "cost": existing.cost,
        }

    # Gather data from forecasting engine
    _engine = sys.modules["zugalife.forecasting.engine"]
    analytics = await _engine.compute_all(session, user_id, days=7)

    # Gather goal progress
    GoalDefinition = sys.modules["zugalife.goals.models"].GoalDefinition
    goals_result = await session.execute(
        select(GoalDefinition).where(
            GoalDefinition.user_id == user_id,
            GoalDefinition.is_completed == False,
        )
    )
    goals = goals_result.scalars().all()

    goal_summaries = []
    for g in goals:
        total = len(g.milestones)
        done = sum(1 for m in g.milestones if m.is_completed)
        identity = getattr(g, "identity_statement", None)
        goal_summaries.append({
            "title": g.title,
            "progress": f"{done}/{total}",
            "identity": identity,
        })

    # Gather gamification data
    UserXP = sys.modules["zugalife.gamification.models"].UserXP
    xp_result = await session.execute(
        select(UserXP).where(UserXP.user_id == user_id)
    )
    user_xp = xp_result.scalar_one_or_none()

    # Build prompt
    prompt = _build_narrative_prompt(analytics, goal_summaries, user_xp)

    # Call AI
    try:
        from core.ai.gateway import ai_call, CreditBlockedError
        response = await ai_call(
            prompt=prompt,
            task="summarization",
            max_tokens=600,
            user_id=user_id,
            user_email=user_email,
        )
    except CreditBlockedError:
        return {"narrative": None, "highlights": [], "error": "Insufficient ZugaTokens"}
    except Exception as e:
        logger.warning("Weekly narrative AI call failed: %s", e)
        return {"narrative": None, "highlights": [], "error": str(e)}

    # Parse response — expect narrative text, optionally with ### Highlights section
    narrative_text = response.content.strip()
    highlights = []

    if "### Highlights" in narrative_text or "**Highlights**" in narrative_text:
        parts = narrative_text.split("### Highlights" if "### Highlights" in narrative_text else "**Highlights**")
        narrative_text = parts[0].strip()
        if len(parts) > 1:
            highlight_lines = parts[1].strip().split("\n")
            highlights = [
                line.lstrip("- *").rstrip("*").strip()
                for line in highlight_lines
                if line.strip() and not line.strip().startswith("#")
            ][:5]

    # Cache
    record = WeeklyNarrative(
        user_id=user_id,
        week_start=week_start,
        narrative=narrative_text,
        highlights="\n".join(highlights) if highlights else "",
        model_used=response.model or "unknown",
        cost=response.cost or 0.0,
    )
    session.add(record)
    await session.flush()

    return {
        "narrative": narrative_text,
        "highlights": highlights,
        "generated_at": record.created_at.isoformat() if record.created_at else None,
        "cached": False,
        "cost": response.cost,
    }


def _build_narrative_prompt(analytics: dict, goals: list[dict], user_xp) -> str:
    """Build the AI prompt for weekly narrative generation."""
    # Extract key stats
    trend = analytics.get("trend", {})
    trend_dir = trend.get("direction", "unknown")
    trend_avg = trend.get("avg_valence", 0)

    # Habit correlations
    habit_corrs_data = analytics.get("habit_correlations", {})
    habit_corrs = habit_corrs_data.get("habits", []) if isinstance(habit_corrs_data, dict) else []
    top_habits = []
    for hc in habit_corrs[:3]:
        if isinstance(hc, dict) and hc.get("correlation_label"):
            top_habits.append(f"{hc.get('habit_name', '?')}: {hc['correlation_label']}")

    # Meditation effectiveness
    med = analytics.get("meditation_effectiveness", {})
    med_avg_shift = med.get("avg_mood_shift", 0) if isinstance(med, dict) else 0

    # Day of week patterns
    dow = analytics.get("day_of_week", {})
    best_day = dow.get("best_day", {}).get("day", "unknown") if isinstance(dow, dict) else "unknown"

    # Goals
    goals_text = "\n".join(
        f"- {g['title']}: {g['progress']} milestones" + (f" (identity: {g['identity']})" if g.get('identity') else "")
        for g in goals
    ) if goals else "No active goals."

    # Streak/consistency
    streak = user_xp.current_streak_days if user_xp else 0
    level = user_xp.level if user_xp else 1

    return f"""Write a warm, insightful weekly wellness summary for a user. 3-4 short paragraphs.

<data>
Mood trend: {trend_dir} (average valence: {trend_avg:.1f} on -3 to +3 scale)
Best day of week: {best_day}
Top habit-mood correlations: {', '.join(top_habits) if top_habits else 'not enough data yet'}
Meditation mood shift (avg): {med_avg_shift:+.1f} points per session
Current streak: {streak} days | Level: {level}
Total mood entries this week: {analytics.get('total_entries', 0)}

Active goals:
{goals_text}
</data>

Guidelines:
1. Start with how their week went emotionally (the trend).
2. Highlight 1-2 patterns worth noticing (habit correlations, best/worst days).
3. If they have identity statements on goals, reinforce those identities.
4. End with one specific, actionable suggestion for next week.
5. Be warm but data-grounded. Reference actual numbers. No generic advice.
6. If there's insufficient data (<3 entries), acknowledge it gently and encourage continued tracking.
7. Keep it under 200 words. No headers, no bullet points in the narrative itself.

After the narrative, add:
### Highlights
- (2-3 one-line highlights, each starting with a dash)"""


def _parse_highlights(raw: str | None) -> list[str]:
    """Parse stored highlights string back to list."""
    if not raw:
        return []
    return [line.strip() for line in raw.split("\n") if line.strip()]
