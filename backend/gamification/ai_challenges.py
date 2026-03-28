"""AI-generated challenge engine for ZugaLife gamification.

Generates personalized daily challenges (3/day) and weekly quests (1-2/week)
based on the user's active habits, goals, streak data, and completion history.

Titles are 2-3 words max. Challenges are realistic — based on what the user
actually does, not aspirational targets they've never hit.

Uses Venice LLM (Kimi-k2.5) via the ai gateway. Falls back to the static
CHALLENGE_POOL if AI generation fails or user has 0 tokens.
"""

import json
import logging
import sys
from datetime import date, timedelta

from sqlalchemy import func, select

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User context gathering (reads cross-module tables)
# ---------------------------------------------------------------------------

async def _gather_user_context(session, user_id: str) -> dict:
    """Collect the user's habits, goals, streaks, and recent activity.

    Returns a dict with everything the LLM needs to generate relevant challenges.
    """
    HabitDefinition = sys.modules["zugalife.habits.models"].HabitDefinition
    HabitLog = sys.modules["zugalife.habits.models"].HabitLog
    GoalDefinition = sys.modules["zugalife.goals.models"].GoalDefinition
    UserXP = sys.modules["zugalife.gamification.models"].UserXP

    today = date.today()
    week_ago = today - timedelta(days=7)

    # Active habits
    habits_result = await session.execute(
        select(HabitDefinition).where(
            HabitDefinition.user_id == user_id,
            HabitDefinition.is_active == True,
        )
    )
    habits = habits_result.scalars().all()

    habit_context = []
    for h in habits:
        # Count completions in last 7 days
        count_result = await session.execute(
            select(func.count()).where(
                HabitLog.user_id == user_id,
                HabitLog.habit_id == h.id,
                HabitLog.completed == True,
                HabitLog.log_date >= week_ago,
            )
        )
        completions_7d = count_result.scalar() or 0
        habit_context.append({
            "name": h.name,
            "emoji": h.emoji,
            "weekly_target": h.weekly_target,
            "completions_last_7d": completions_7d,
        })

    # Active goals with milestones
    goals_result = await session.execute(
        select(GoalDefinition).where(
            GoalDefinition.user_id == user_id,
            GoalDefinition.is_completed == False,
        )
    )
    goals = goals_result.scalars().all()

    goal_context = []
    for g in goals:
        total_ms = len(g.milestones)
        done_ms = sum(1 for m in g.milestones if m.is_completed)
        next_milestone = next((m.title for m in g.milestones if not m.is_completed), None)
        goal_context.append({
            "title": g.title,
            "milestones_done": done_ms,
            "milestones_total": total_ms,
            "next_milestone": next_milestone,
            "deadline": g.deadline.isoformat() if g.deadline else None,
        })

    # Streak and level
    xp_result = await session.execute(
        select(UserXP).where(UserXP.user_id == user_id)
    )
    user_xp = xp_result.scalar_one_or_none()

    streak_days = user_xp.current_streak_days if user_xp else 0
    level = user_xp.level if user_xp else 1

    return {
        "habits": habit_context,
        "goals": goal_context,
        "streak_days": streak_days,
        "level": level,
        "today": today.isoformat(),
        "day_of_week": today.strftime("%A"),
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_challenge_prompt(context: dict, challenge_type: str = "daily") -> str:
    """Build the LLM prompt for challenge generation.

    challenge_type: "daily" (3 challenges) or "weekly" (1-2 quests)
    """
    habits_text = ""
    if context["habits"]:
        lines = []
        for h in context["habits"]:
            target_note = f" (target: {h['weekly_target']}x/week)" if h.get("weekly_target") else ""
            lines.append(f"- {h['emoji']} {h['name']}: {h['completions_last_7d']}/7 days completed{target_note}")
        habits_text = "\n".join(lines)
    else:
        habits_text = "No active habits yet."

    goals_text = ""
    if context["goals"]:
        lines = []
        for g in context["goals"]:
            progress = f"{g['milestones_done']}/{g['milestones_total']} milestones"
            next_ms = f" — next: {g['next_milestone']}" if g.get("next_milestone") else ""
            lines.append(f"- {g['title']}: {progress}{next_ms}")
        goals_text = "\n".join(lines)
    else:
        goals_text = "No active goals yet."

    if challenge_type == "daily":
        return f"""Generate 3 daily challenges for a wellness app user. Today is {context['day_of_week']}, {context['today']}.

<user_context>
Level: {context['level']}
Current streak: {context['streak_days']} days

Active habits:
{habits_text}

Active goals:
{goals_text}
</user_context>

Rules:
1. Each challenge title MUST be exactly 2-3 words. No more.
2. Description is one short sentence (under 60 characters).
3. XP reward: 20-50 based on difficulty.
4. Challenges must be achievable TODAY based on what the user actually does.
5. Mix: some connected to user's habits/goals, some general wellness (mood, journal, meditation).
6. NEVER suggest something unrealistic. If user completes a habit 2/7 days, don't ask for "perfect day".
7. If user has no habits or goals, generate general wellness challenges only.
8. Each challenge MUST include a "source" field — the action that completes it. Valid sources: mood_log, habit_check, journal_entry, meditation_complete, therapist_session, goal_milestone.

Return ONLY valid JSON array, no markdown, no explanation:
[
  {{"key": "unique_key", "title": "Two Words", "desc": "Short description under 60 chars", "xp": 25, "source": "mood_log"}},
  ...
]"""

    else:  # weekly
        return f"""Generate 1-2 weekly quests for a wellness app user. Week starting {context['today']}.

<user_context>
Level: {context['level']}
Current streak: {context['streak_days']} days

Active habits:
{habits_text}

Active goals:
{goals_text}
</user_context>

Rules:
1. Each quest title MUST be exactly 2-3 words. No more.
2. Description is one short sentence (under 80 characters).
3. XP reward: 75-150 based on difficulty.
4. Quests span the full week — multi-day objectives.
5. Connect to the user's actual habits/goals when possible.
6. Be realistic: if user averages 3/7 habit days, a quest for "5 out of 7" is good. "7 out of 7" is not.
7. If user has no habits or goals, generate general wellness quests.
8. Each quest MUST include a "source" field — the primary action type. Valid sources: mood_log, habit_check, journal_entry, meditation_complete, therapist_session, goal_milestone.

Return ONLY valid JSON array, no markdown, no explanation:
[
  {{"key": "unique_key", "title": "Two Words", "desc": "Short description under 80 chars", "xp": 100, "source": "habit_check"}},
  ...
]"""


# ---------------------------------------------------------------------------
# Source inference (fallback if LLM omits source field)
# ---------------------------------------------------------------------------

def _infer_source_from_desc(desc: str) -> str:
    """Best-effort guess at completion source from description text."""
    desc_lower = desc.lower()
    if any(w in desc_lower for w in ("mood", "check-in", "checkin", "feeling")):
        return "mood_log"
    if any(w in desc_lower for w in ("habit", "complete all", "streak")):
        return "habit_check"
    if any(w in desc_lower for w in ("journal", "write", "entry", "diary")):
        return "journal_entry"
    if any(w in desc_lower for w in ("meditat", "mindful", "breathe", "calm")):
        return "meditation_complete"
    if any(w in desc_lower for w in ("therapist", "session", "talk")):
        return "therapist_session"
    if any(w in desc_lower for w in ("goal", "milestone")):
        return "goal_milestone"
    return "habit_check"  # safe default


# Static challenge source mapping (for the fallback CHALLENGE_POOL)
STATIC_CHALLENGE_SOURCES: dict[str, str] = {
    "log_mood_2x": "mood_log",
    "meditate_today": "meditation_complete",
    "journal_entry": "journal_entry",
    "all_habits": "habit_check",
    "therapist_session": "therapist_session",
    "long_meditation": "meditation_complete",
    "reflect_journal": "journal_entry",
    "habit_streak_3": "habit_check",
}


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------

async def generate_challenges(
    session,
    user_id: str,
    challenge_type: str = "daily",
    user_email: str | None = None,
) -> list[dict] | None:
    """Generate AI-powered challenges. Returns list of challenge dicts or None on failure."""
    try:
        _gateway = sys.modules.get("zugalife.ai.gateway") or __import__(
            "core.ai.gateway", fromlist=["ai_call"]
        )
        ai_call = getattr(_gateway, "ai_call", None)
        if ai_call is None:
            # Try the standalone gateway
            from core.ai.gateway import ai_call
    except Exception:
        logger.warning("AI gateway not available, falling back to static challenges")
        return None

    context = await _gather_user_context(session, user_id)

    prompt = _build_challenge_prompt(context, challenge_type)

    try:
        response = await ai_call(
            prompt=prompt,
            task=f"challenge_gen_{challenge_type}",
            max_tokens=512,
            user_id=user_id,
            user_email=user_email,
        )

        # Parse JSON from response
        text = response.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        challenges = json.loads(text)

        if not isinstance(challenges, list):
            logger.warning("AI returned non-list: %s", type(challenges))
            return None

        # Validate and sanitize
        validated = []
        for c in challenges:
            if not isinstance(c, dict):
                continue
            title = str(c.get("title", "")).strip()
            # Enforce 2-3 word titles
            words = title.split()
            if len(words) < 2 or len(words) > 3:
                title = " ".join(words[:3]) if words else "Daily Task"

            key = str(c.get("key", f"ai_{title.lower().replace(' ', '_')}")).strip()
            desc = str(c.get("desc", "")).strip()[:80]
            xp = int(c.get("xp", 25))
            # Clamp XP to reasonable range
            if challenge_type == "daily":
                xp = max(15, min(50, xp))
            else:
                xp = max(50, min(150, xp))

            # Extract and validate completion source
            VALID_SOURCES = {"mood_log", "habit_check", "journal_entry", "meditation_complete", "therapist_session", "goal_milestone"}
            source = str(c.get("source", "")).strip()
            if source not in VALID_SOURCES:
                source = _infer_source_from_desc(desc)

            validated.append({
                "key": f"ai_{key}" if not key.startswith("ai_") else key,
                "title": title,
                "desc": desc,
                "xp": xp,
                "source": source,
            })

        if not validated:
            logger.warning("AI returned no valid challenges after validation")
            return None

        logger.info(
            "AI generated %d %s challenges for user %s",
            len(validated), challenge_type, user_id[:8],
        )
        return validated

    except json.JSONDecodeError as e:
        logger.warning("AI challenge JSON parse failed: %s", e)
        return None
    except Exception as e:
        logger.warning("AI challenge generation failed: %s: %s", type(e).__name__, e)
        return None
