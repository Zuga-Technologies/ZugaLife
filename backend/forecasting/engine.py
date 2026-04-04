"""Mood forecasting engine — pure statistics, no AI calls.

All 6 analytics computed on-demand from raw mood/habit/meditation data.
Nothing is stored — results are ephemeral.

Valence scoring: each mood label maps to a score from -3 (Angry) to +3
(Motivated/Excited). This is the foundation all calculations build on.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import desc, func, select

# ── Valence Map ──────────────────────────────────────────────────────

MOOD_VALENCE: dict[str, int] = {
    "Motivated": 3,
    "Excited": 3,
    "Happy": 2,
    "Loved": 2,
    "Calm": 1,
    "Thoughtful": 0,
    "Neutral": 0,
    "Tired": -1,
    "Sad": -2,
    "Frustrated": -2,
    "Anxious": -2,
    "Angry": -3,
}

# Emoji → label fallback (for meditation mood_before/mood_after which store emoji)
EMOJI_VALENCE: dict[str, int] = {
    "\U0001f4aa": 3,   # 💪 Motivated
    "\U0001f929": 3,   # 🤩 Excited
    "\U0001f60a": 2,   # 😊 Happy
    "\U0001f970": 2,   # 🥰 Loved
    "\U0001f60c": 1,   # 😌 Calm
    "\U0001f914": 0,   # 🤔 Thoughtful
    "\U0001f610": 0,   # 😐 Neutral
    "\U0001f634": -1,  # 😴 Tired
    "\U0001f622": -2,  # 😢 Sad
    "\U0001f624": -2,  # 😤 Frustrated
    "\U0001f630": -2,  # 😰 Anxious
    "\U0001f620": -3,  # 😠 Angry
}


def valence(label: str) -> int | None:
    """Get valence score from a mood label or emoji."""
    if label in MOOD_VALENCE:
        return MOOD_VALENCE[label]
    return EMOJI_VALENCE.get(label)


# ── Data Fetching ────────────────────────────────────────────────────

async def _fetch_mood_entries(session, user_id: str, days: int):
    """Fetch mood entries for the last N days."""
    MoodEntry = sys.modules["zugalife.models"].MoodEntry
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(MoodEntry.label, MoodEntry.created_at)
        .where(MoodEntry.user_id == user_id, MoodEntry.created_at >= since)
        .order_by(MoodEntry.created_at)
    )
    return result.all()


async def _fetch_habit_completions(session, user_id: str, days: int):
    """Fetch habit completion data grouped by date and habit."""
    _h = sys.modules["zugalife.habits.models"]
    HabitDefinition = _h.HabitDefinition
    HabitLog = _h.HabitLog

    since = date.today() - timedelta(days=days)

    # Get active habits (include unit + target for amount correlations)
    habits_result = await session.execute(
        select(
            HabitDefinition.id, HabitDefinition.name, HabitDefinition.emoji,
            HabitDefinition.unit, HabitDefinition.default_target,
        )
        .where(HabitDefinition.user_id == user_id, HabitDefinition.is_active == True)
    )
    habits = habits_result.all()

    # Get completed logs (include amount for quantified correlations)
    logs_result = await session.execute(
        select(HabitLog.habit_id, HabitLog.log_date, HabitLog.amount)
        .where(
            HabitLog.user_id == user_id,
            HabitLog.log_date >= since,
            HabitLog.completed == True,
        )
    )
    logs = logs_result.all()

    # Build a set of (habit_id, date) pairs for quick lookup
    completed_set = {(log.habit_id, log.log_date) for log in logs}

    # Build amount map: (habit_id, date) → amount (for quantified habits)
    amount_map = {}
    for log in logs:
        if log.amount is not None:
            amount_map[(log.habit_id, log.log_date)] = log.amount

    return habits, completed_set, amount_map


async def _fetch_meditation_moods(session, user_id: str, days: int):
    """Fetch meditation sessions with before/after moods."""
    MeditationSession = sys.modules["zugalife.meditation.models"].MeditationSession
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(
            MeditationSession.mood_before,
            MeditationSession.mood_after,
            MeditationSession.created_at,
        )
        .where(
            MeditationSession.user_id == user_id,
            MeditationSession.created_at >= since,
            MeditationSession.mood_before.isnot(None),
            MeditationSession.mood_after.isnot(None),
        )
        .order_by(MeditationSession.created_at)
    )
    return result.all()


# ── Analysis Functions ───────────────────────────────────────────────

def _to_date(dt) -> date:
    """Convert datetime or string to date."""
    if isinstance(dt, str):
        return date.fromisoformat(dt[:10])
    if isinstance(dt, datetime):
        return dt.date()
    return dt


def compute_trend(entries, days: int) -> dict:
    """Linear regression on daily average valence.

    Returns slope (valence points per day), direction label,
    and a clinical-neutral description.
    """
    if len(entries) < 3:
        return {"slope": 0.0, "direction": "insufficient_data",
                "description": "Not enough data to identify a trend yet."}

    # Group entries by date → daily average valence
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    if len(by_date) < 3:
        return {"slope": 0.0, "direction": "insufficient_data",
                "description": "Not enough days with data to identify a trend."}

    # Daily averages, indexed by days from start
    sorted_dates = sorted(by_date.keys())
    base = sorted_dates[0]
    xs = [(d - base).days for d in sorted_dates]
    ys = [sum(by_date[d]) / len(by_date[d]) for d in sorted_dates]

    # Simple least-squares linear regression
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        slope = 0.0
    else:
        slope = (n * sum_xy - sum_x * sum_y) / denom

    # Classify direction
    if abs(slope) < 0.02:
        direction = "stable"
        desc_text = "Your overall mood has been relatively steady."
    elif slope > 0.1:
        direction = "improving"
        desc_text = "Your mood has been on a noticeable upward trend."
    elif slope > 0:
        direction = "slightly_improving"
        desc_text = "There's a slight positive shift in your mood pattern."
    elif slope < -0.1:
        direction = "declining"
        desc_text = "Your mood has been trending lower recently."
    else:
        direction = "slightly_declining"
        desc_text = "There's been a slight dip in your mood pattern."

    # Average valence for context
    avg = sum_y / n

    return {
        "slope": round(slope, 4),
        "direction": direction,
        "description": desc_text,
        "avg_valence": round(avg, 2),
        "data_points": n,
    }


def compute_day_of_week(entries) -> dict:
    """Average valence by day of week.

    Returns per-day averages and identifies best/lowest days.
    """
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]

    by_day: dict[int, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            weekday = _to_date(entry.created_at).weekday()
            by_day[weekday].append(v)

    if not by_day:
        return {"days": [], "description": "No mood data available."}

    days = []
    for i in range(7):
        scores = by_day.get(i, [])
        if scores:
            avg = sum(scores) / len(scores)
            days.append({
                "day": DAY_NAMES[i],
                "avg_valence": round(avg, 2),
                "entries": len(scores),
            })
        else:
            days.append({
                "day": DAY_NAMES[i],
                "avg_valence": None,
                "entries": 0,
            })

    # Find best and lowest days (only from days with data)
    with_data = [d for d in days if d["avg_valence"] is not None]
    if len(with_data) < 2:
        desc_text = "Need data across more days to identify weekly patterns."
    else:
        best = max(with_data, key=lambda d: d["avg_valence"])
        lowest = min(with_data, key=lambda d: d["avg_valence"])
        if best["avg_valence"] == lowest["avg_valence"]:
            desc_text = "Your mood is fairly consistent across the week."
        else:
            desc_text = (
                f"You tend to feel best on {best['day']}s "
                f"and lowest on {lowest['day']}s."
            )

    return {"days": days, "description": desc_text}


def compute_forecast(entries) -> dict:
    """Next-day mood forecast using exponential weighted moving average
    with day-of-week seasonal adjustment.

    EWMA gives more weight to recent moods. The day-of-week adjustment
    captures weekly patterns (e.g., Monday blues).
    """
    if len(entries) < 5:
        return {"forecast_valence": None, "forecast_label": None,
                "confidence": "low",
                "description": "Need at least 5 mood entries to generate a forecast."}

    # Compute EWMA on daily averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    sorted_dates = sorted(by_date.keys())
    daily_avgs = [sum(by_date[d]) / len(by_date[d]) for d in sorted_dates]

    # EWMA with alpha=0.3 (moderate smoothing)
    alpha = 0.3
    ewma = daily_avgs[0]
    for val in daily_avgs[1:]:
        ewma = alpha * val + (1 - alpha) * ewma

    # Day-of-week adjustment for tomorrow
    tomorrow = date.today() + timedelta(days=1)
    tomorrow_weekday = tomorrow.weekday()

    by_weekday: dict[int, list[float]] = defaultdict(list)
    for d in sorted_dates:
        by_weekday[d.weekday()].append(sum(by_date[d]) / len(by_date[d]))

    overall_avg = sum(daily_avgs) / len(daily_avgs)
    weekday_scores = by_weekday.get(tomorrow_weekday, [])
    if weekday_scores:
        weekday_avg = sum(weekday_scores) / len(weekday_scores)
        seasonal_adj = weekday_avg - overall_avg
    else:
        seasonal_adj = 0.0

    forecast = ewma + seasonal_adj
    forecast = max(-3.0, min(3.0, forecast))  # clamp

    # Map forecast to nearest mood label
    forecast_label = _valence_to_label(forecast)

    # Confidence based on data volume and consistency
    if len(sorted_dates) >= 14:
        confidence = "moderate"
    else:
        confidence = "low"

    return {
        "forecast_valence": round(forecast, 2),
        "forecast_label": forecast_label,
        "confidence": confidence,
        "method": "ewma_seasonal",
        "description": (
            f"Based on recent patterns, tomorrow may feel "
            f"around '{forecast_label}' territory."
        ),
    }


def compute_habit_correlations(
    entries, habits, completed_set,
) -> dict:
    """Compare average mood on days WITH vs WITHOUT each habit completion.

    A positive delta means mood tends to be higher on days the habit
    is completed. This is correlation, not causation.
    """
    if not habits or not entries:
        return {"habits": [], "description": "No habit or mood data to compare."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if not daily_mood:
        return {"habits": [], "description": "No mood data available."}

    mood_dates = set(daily_mood.keys())
    results = []

    for habit in habits:
        habit_dates = {
            log_date for (hid, log_date) in completed_set
            if hid == habit.id
        }

        # Only consider dates where we have BOTH mood and habit data
        with_habit = [daily_mood[d] for d in mood_dates if d in habit_dates]
        without_habit = [daily_mood[d] for d in mood_dates if d not in habit_dates]

        if not with_habit or not without_habit:
            continue

        avg_with = sum(with_habit) / len(with_habit)
        avg_without = sum(without_habit) / len(without_habit)
        delta = avg_with - avg_without

        results.append({
            "habit_name": habit.name,
            "habit_emoji": habit.emoji,
            "avg_mood_with": round(avg_with, 2),
            "avg_mood_without": round(avg_without, 2),
            "delta": round(delta, 2),
            "days_with": len(with_habit),
            "days_without": len(without_habit),
        })

    # Sort by delta descending (most positive correlation first)
    results.sort(key=lambda r: r["delta"], reverse=True)

    if not results:
        desc_text = "Not enough overlapping mood and habit data yet."
    else:
        top = results[0]
        if top["delta"] > 0.5:
            desc_text = (
                f"Days you complete '{top['habit_name']}' tend to average "
                f"{abs(top['delta']):.1f} points higher on the mood scale."
            )
        elif top["delta"] < -0.5:
            desc_text = (
                f"Interestingly, '{top['habit_name']}' days tend to have "
                f"slightly lower mood — worth exploring why."
            )
        else:
            desc_text = "No strong mood-habit correlations detected yet."

    return {"habits": results, "description": desc_text}


def compute_habit_amount_correlations(
    entries, habits, amount_map: dict,
) -> dict:
    """Pearson correlation between habit AMOUNTS and mood valence.

    Unlike binary habit correlations (did/didn't do it), this measures
    whether MORE of a habit predicts better mood. Only works for habits
    with a unit (e.g., "45 minutes of exercise", "8 glasses of water").

    Pearson r ranges from -1 to +1:
      +1 = perfect positive (more amount → better mood)
       0 = no linear relationship
      -1 = perfect negative (more amount → worse mood)
    """
    if not habits or not entries or not amount_map:
        return {"habits": [], "description": "No quantified habit data to analyze."}

    # Filter to habits that have a unit (quantified)
    quantified_habits = [h for h in habits if h.unit]
    if not quantified_habits:
        return {"habits": [], "description": "No habits with measurable amounts (units) set."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if not daily_mood:
        return {"habits": [], "description": "No mood data available."}

    mood_dates = set(daily_mood.keys())
    results = []

    for habit in quantified_habits:
        # Collect paired data: (amount, mood) for days with both
        pairs: list[tuple[float, float]] = []
        for d in mood_dates:
            key = (habit.id, d)
            if key in amount_map:
                pairs.append((amount_map[key], daily_mood[d]))

        if len(pairs) < 3:
            continue  # need at least 3 data points for Pearson

        amounts = [p[0] for p in pairs]
        moods = [p[1] for p in pairs]

        # Check variance — Pearson undefined if either variable is constant
        if len(set(amounts)) < 2 or len(set(moods)) < 2:
            continue

        # Compute Pearson r manually (no numpy dependency)
        n = len(pairs)
        sum_x = sum(amounts)
        sum_y = sum(moods)
        sum_xy = sum(x * y for x, y in pairs)
        sum_x2 = sum(x * x for x in amounts)
        sum_y2 = sum(y * y for y in moods)

        numerator = n * sum_xy - sum_x * sum_y
        denom_x = n * sum_x2 - sum_x * sum_x
        denom_y = n * sum_y2 - sum_y * sum_y

        if denom_x <= 0 or denom_y <= 0:
            continue

        r = numerator / math.sqrt(denom_x * denom_y)

        # Compute t-statistic for significance (p-value approximation)
        if abs(r) >= 1.0:
            p_value = 0.0
        else:
            t_stat = r * math.sqrt((n - 2) / (1 - r * r))
            # Rough p-value using t-distribution approximation (2-tailed)
            # For small n, this is approximate but sufficient for our purposes
            df = n - 2
            p_value = 2.0 * (1.0 - _t_cdf_approx(abs(t_stat), df))

        # Interpret strength
        abs_r = abs(r)
        if abs_r < 0.2:
            strength = "negligible"
        elif abs_r < 0.4:
            strength = "weak"
        elif abs_r < 0.6:
            strength = "moderate"
        elif abs_r < 0.8:
            strength = "strong"
        else:
            strength = "very_strong"

        results.append({
            "habit_name": habit.name,
            "habit_emoji": habit.emoji,
            "unit": habit.unit,
            "r": round(r, 3),
            "p_value": round(p_value, 4),
            "strength": strength,
            "significant": p_value < 0.05,
            "data_points": n,
            "avg_amount": round(sum_x / n, 1),
            "direction": "positive" if r > 0 else "negative" if r < 0 else "none",
        })

    # Sort by absolute r (strongest correlation first)
    results.sort(key=lambda r: abs(r["r"]), reverse=True)

    if not results:
        desc_text = "Not enough overlapping amount and mood data for quantified habits."
    else:
        top = results[0]
        if top["significant"] and top["strength"] not in ("negligible",):
            direction = "more" if top["r"] > 0 else "less"
            desc_text = (
                f"{top['strength'].capitalize()} {top['direction']} correlation: "
                f"{direction} {top['unit']} of '{top['habit_name']}' "
                f"tends to align with {'higher' if top['r'] > 0 else 'lower'} mood "
                f"(r={top['r']:.2f}, p={top['p_value']:.3f})."
            )
        else:
            desc_text = "No statistically significant amount-mood correlations detected yet."

    return {"habits": results, "description": desc_text}


async def _fetch_meditation_sessions_full(session, user_id: str, days: int):
    """Fetch meditation sessions with type, duration, and mood data."""
    MeditationSession = sys.modules["zugalife.meditation.models"].MeditationSession
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(
            MeditationSession.type,
            MeditationSession.duration_seconds,
            MeditationSession.ambience,
            MeditationSession.mood_before,
            MeditationSession.mood_after,
            MeditationSession.created_at,
        )
        .where(
            MeditationSession.user_id == user_id,
            MeditationSession.created_at >= since,
            MeditationSession.mood_before.isnot(None),
            MeditationSession.mood_after.isnot(None),
        )
        .order_by(MeditationSession.created_at)
    )
    return result.all()


def compute_meditation_type_breakdown(med_sessions) -> dict:
    """Break down meditation effectiveness by type, duration, and ambience.

    Unlike the aggregate meditation_effectiveness (which lumps all sessions),
    this answers: which TYPE works best for you? Does duration matter?
    Which ambience produces the biggest mood shift?

    Uses group comparison — average mood delta per category. Reports
    confidence based on sample size per group (n >= 3 to report).
    """
    if not med_sessions:
        return {
            "by_type": [],
            "by_duration": [],
            "by_ambience": [],
            "description": "No meditation sessions with before/after mood data.",
        }

    # Parse all sessions into (type, duration, ambience, delta)
    parsed = []
    for s in med_sessions:
        before = valence(s.mood_before)
        after = valence(s.mood_after)
        if before is not None and after is not None:
            parsed.append({
                "type": s.type or "unknown",
                "duration": (s.duration_seconds or 0) // 60,
                "ambience": s.ambience or "unknown",
                "delta": after - before,
            })

    if not parsed:
        return {
            "by_type": [],
            "by_duration": [],
            "by_ambience": [],
            "description": "No sessions with valid mood comparisons.",
        }

    def _group_stats(key: str) -> list[dict]:
        """Compute avg delta and stats per group."""
        groups: dict[str, list[int]] = defaultdict(list)
        for p in parsed:
            groups[p[key]].append(p["delta"])

        results = []
        for name, deltas in sorted(groups.items(), key=lambda x: -len(x[1])):
            n = len(deltas)
            if n < 2:
                continue  # need at least 2 sessions to compare
            avg = sum(deltas) / n
            improved = sum(1 for d in deltas if d > 0)
            worsened = sum(1 for d in deltas if d < 0)

            # Standard error for confidence
            if n >= 2:
                variance = sum((d - avg) ** 2 for d in deltas) / (n - 1)
                std_err = math.sqrt(variance / n) if variance > 0 else 0
            else:
                std_err = 0

            results.append({
                "name": str(name),
                "avg_delta": round(avg, 2),
                "sessions": n,
                "improved": improved,
                "worsened": worsened,
                "std_error": round(std_err, 2),
                "reliable": n >= 3,  # minimum for trust
            })

        # Sort by avg_delta descending (best first)
        results.sort(key=lambda x: x["avg_delta"], reverse=True)
        return results

    by_type = _group_stats("type")
    by_duration = _group_stats("duration")
    by_ambience = _group_stats("ambience")

    # Generate description from the best type
    if by_type:
        reliable = [t for t in by_type if t["reliable"]]
        if reliable:
            best = reliable[0]
            desc_text = (
                f"'{best['name']}' meditation shows the strongest mood improvement "
                f"(+{best['avg_delta']:.1f} avg across {best['sessions']} sessions)."
            )
            if len(reliable) > 1:
                worst = reliable[-1]
                desc_text += (
                    f" '{worst['name']}' shows the least effect "
                    f"({worst['avg_delta']:+.1f})."
                )
        else:
            desc_text = "Need more sessions per type (3+ each) to compare effectively."
    else:
        desc_text = "Not enough meditation data to analyze by type."

    return {
        "by_type": by_type,
        "by_duration": by_duration,
        "by_ambience": by_ambience,
        "description": desc_text,
    }


async def _fetch_therapist_dates(session, user_id: str, days: int) -> set[date]:
    """Fetch dates when user had therapist sessions."""
    _models = sys.modules["zugalife.therapist.models"]
    TherapistSessionNote = _models.TherapistSessionNote
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(TherapistSessionNote.created_at)
        .where(TherapistSessionNote.user_id == user_id, TherapistSessionNote.created_at >= since)
    )
    return {_to_date(row.created_at) for row in result.all()}


def compute_engagement_correlations(
    entries, journal_dates: set[date], therapist_dates: set[date],
) -> dict:
    """Correlate self-reflection engagement with mood.

    Three analyses:
    1. Journal days vs non-journal days (binary delta)
    2. Therapist session days vs non-session days (binary delta)
    3. Any engagement (journal OR therapy) vs none

    Same delta method as habit_correlations — avg mood on days
    with the behavior vs days without.
    """
    if not entries:
        return {"journal": None, "therapist": None, "any_engagement": None,
                "description": "No mood data available."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if not daily_mood:
        return {"journal": None, "therapist": None, "any_engagement": None,
                "description": "No mood data available."}

    mood_dates = set(daily_mood.keys())

    def _binary_delta(activity_dates: set[date], label: str) -> dict | None:
        """Compute mood delta for days with vs without an activity."""
        with_activity = [daily_mood[d] for d in mood_dates if d in activity_dates]
        without_activity = [daily_mood[d] for d in mood_dates if d not in activity_dates]

        if not with_activity or not without_activity:
            return None

        avg_with = sum(with_activity) / len(with_activity)
        avg_without = sum(without_activity) / len(without_activity)
        delta = avg_with - avg_without

        return {
            "label": label,
            "avg_mood_with": round(avg_with, 2),
            "avg_mood_without": round(avg_without, 2),
            "delta": round(delta, 2),
            "days_with": len(with_activity),
            "days_without": len(without_activity),
        }

    journal_result = _binary_delta(journal_dates, "journaling")
    therapist_result = _binary_delta(therapist_dates, "therapist")

    # Combined: any self-reflection activity
    any_engagement_dates = journal_dates | therapist_dates
    engagement_result = _binary_delta(any_engagement_dates, "any_reflection")

    # Build description
    parts = []
    for result in [journal_result, therapist_result]:
        if result and abs(result["delta"]) > 0.3:
            direction = "higher" if result["delta"] > 0 else "lower"
            parts.append(
                f"{result['label']} days average {abs(result['delta']):.1f} points "
                f"{direction} mood"
            )

    if parts:
        desc_text = "Self-reflection impact: " + "; ".join(parts) + "."
    elif engagement_result and abs(engagement_result["delta"]) > 0.3:
        direction = "higher" if engagement_result["delta"] > 0 else "lower"
        desc_text = (
            f"Days with any self-reflection (journal or therapy) show "
            f"{abs(engagement_result['delta']):.1f} points {direction} mood."
        )
    else:
        desc_text = "No strong mood difference between reflection and non-reflection days yet."

    return {
        "journal": journal_result,
        "therapist": therapist_result,
        "any_engagement": engagement_result,
        "description": desc_text,
    }


def compute_interaction_effects(
    entries, habits, completed_set, med_sessions, journal_dates: set[date],
) -> dict:
    """Detect synergistic behavior combinations.

    For every pair of behaviors, compares mood across 4 groups:
      - Both done: avg mood when A AND B happen same day
      - A only: avg mood when A but not B
      - B only: avg mood when B but not A
      - Neither: avg mood when neither happens

    Interaction effect = both - A_only - B_only + neither
    Positive = synergistic (combo is better than sum of parts)
    Negative = redundant (doing both doesn't help more than either alone)

    Only reports pairs with at least 2 days in each group.
    """
    if not entries:
        return {"pairs": [], "description": "No mood data available."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if len(daily_mood) < 7:
        return {"pairs": [], "description": "Need at least 7 days of mood data for interaction analysis."}

    mood_dates = set(daily_mood.keys())

    # Build meditation dates
    med_dates: set[date] = set()
    for s in med_sessions:
        med_dates.add(_to_date(s.created_at))

    # Collect all behavior signals
    signals: list[tuple[str, set[date]]] = []
    for habit in (habits or []):
        habit_dates = {d for (hid, d) in completed_set if hid == habit.id}
        if habit_dates:
            signals.append((habit.name, habit_dates))

    if med_dates:
        signals.append(("Meditation", med_dates))
    if journal_dates:
        signals.append(("Journaling", journal_dates))

    if len(signals) < 2:
        return {"pairs": [], "description": "Need at least 2 tracked behaviors to detect interactions."}

    results = []

    # Test every unique pair
    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            name_a, dates_a = signals[i]
            name_b, dates_b = signals[j]

            # Split mood dates into 4 groups
            both = [daily_mood[d] for d in mood_dates if d in dates_a and d in dates_b]
            a_only = [daily_mood[d] for d in mood_dates if d in dates_a and d not in dates_b]
            b_only = [daily_mood[d] for d in mood_dates if d not in dates_a and d in dates_b]
            neither = [daily_mood[d] for d in mood_dates if d not in dates_a and d not in dates_b]

            # Need at least 2 days in each group for meaningful comparison
            if len(both) < 2 or len(neither) < 2:
                continue
            # Need at least 1 in the solo groups (they can be small)
            if not a_only and not b_only:
                continue

            avg_both = sum(both) / len(both)
            avg_a = sum(a_only) / len(a_only) if a_only else avg_both
            avg_b = sum(b_only) / len(b_only) if b_only else avg_both
            avg_none = sum(neither) / len(neither)

            # Interaction effect: does the combo beat the sum of individual effects?
            # individual_a = avg_a - avg_none (A's solo effect vs baseline)
            # individual_b = avg_b - avg_none (B's solo effect vs baseline)
            # combined = avg_both - avg_none (combo effect vs baseline)
            # interaction = combined - individual_a - individual_b
            #            = avg_both - avg_a - avg_b + avg_none
            interaction = avg_both - avg_a - avg_b + avg_none

            # Combo lift: how much better is both vs the better single?
            best_single = max(avg_a, avg_b)
            combo_lift = avg_both - best_single

            results.append({
                "behavior_a": name_a,
                "behavior_b": name_b,
                "avg_mood_both": round(avg_both, 2),
                "avg_mood_a_only": round(avg_a, 2),
                "avg_mood_b_only": round(avg_b, 2),
                "avg_mood_neither": round(avg_none, 2),
                "interaction_effect": round(interaction, 2),
                "combo_lift": round(combo_lift, 2),
                "synergistic": interaction > 0.2,
                "days_both": len(both),
                "days_a_only": len(a_only),
                "days_b_only": len(b_only),
                "days_neither": len(neither),
            })

    # Sort by interaction effect (strongest synergy first)
    results.sort(key=lambda x: x["interaction_effect"], reverse=True)

    if not results:
        desc_text = "Not enough overlapping behavior data to detect interactions yet."
    else:
        synergies = [r for r in results if r["synergistic"]]
        if synergies:
            top = synergies[0]
            desc_text = (
                f"Synergy detected: '{top['behavior_a']}' + '{top['behavior_b']}' together "
                f"average {top['avg_mood_both']:+.1f} mood — better than either alone "
                f"({top['avg_mood_a_only']:+.1f} / {top['avg_mood_b_only']:+.1f}). "
                f"Interaction effect: {top['interaction_effect']:+.2f}."
            )
        else:
            top = results[0]
            desc_text = (
                f"No strong synergies yet. Best combo: '{top['behavior_a']}' + "
                f"'{top['behavior_b']}' ({top['avg_mood_both']:+.1f} mood on combo days)."
            )

    return {"pairs": results, "description": desc_text}


def compute_lagged_correlations(
    entries, habits, completed_set, med_sessions, journal_dates: set[date],
) -> dict:
    """Correlate today's behaviors with TOMORROW's mood (lag-1 analysis).

    Same-day correlations miss delayed effects: exercise today might not
    feel good today (you're tired), but tomorrow you feel great. This
    computes Pearson r between each behavior on day N and mood on day N+1.

    Compares lag-0 (same-day) vs lag-1 (next-day) r values. If lag-1 > lag-0,
    the behavior has a delayed benefit — a genuinely actionable insight.
    """
    if not entries:
        return {"factors": [], "description": "No mood data available."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if len(daily_mood) < 5:
        return {"factors": [], "description": "Need at least 5 days of mood data for lag analysis."}

    # Build meditation dates set
    med_dates: set[date] = set()
    for s in med_sessions:
        med_dates.add(_to_date(s.created_at))

    # Collect all behavior signals: (name, set_of_dates)
    behavior_signals: list[tuple[str, str, set[date]]] = []

    # Habits
    for habit in (habits or []):
        habit_dates = {d for (hid, d) in completed_set if hid == habit.id}
        if habit_dates:
            behavior_signals.append((habit.name, habit.emoji, habit_dates))

    # Meditation
    if med_dates:
        behavior_signals.append(("Meditation", "🧘", med_dates))

    # Journaling
    if journal_dates:
        behavior_signals.append(("Journaling", "📓", journal_dates))

    if not behavior_signals:
        return {"factors": [], "description": "No behavioral data to correlate."}

    mood_dates_sorted = sorted(daily_mood.keys())
    results = []

    for name, emoji, activity_dates in behavior_signals:
        # Lag-0 (same-day): behavior[d] vs mood[d]
        lag0_pairs = []
        # Lag-1 (next-day): behavior[d] vs mood[d+1]
        lag1_pairs = []

        for d in mood_dates_sorted:
            did_it = 1.0 if d in activity_dates else 0.0

            # Same-day
            if d in daily_mood:
                lag0_pairs.append((did_it, daily_mood[d]))

            # Next-day
            next_day = d + timedelta(days=1)
            if next_day in daily_mood:
                lag1_pairs.append((did_it, daily_mood[next_day]))

        def _pearson(pairs: list[tuple[float, float]]) -> tuple[float, float] | None:
            """Compute Pearson r + p-value from (x, y) pairs."""
            if len(pairs) < 5:
                return None
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            if len(set(xs)) < 2 or len(set(ys)) < 2:
                return None

            n = len(pairs)
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xy = sum(x * y for x, y in pairs)
            sum_x2 = sum(x * x for x in xs)
            sum_y2 = sum(y * y for y in ys)

            num = n * sum_xy - sum_x * sum_y
            dx = n * sum_x2 - sum_x * sum_x
            dy = n * sum_y2 - sum_y * sum_y

            if dx <= 0 or dy <= 0:
                return None

            r = num / math.sqrt(dx * dy)
            if abs(r) >= 1.0:
                return (r, 0.0)

            t_stat = r * math.sqrt((n - 2) / (1 - r * r))
            p = 2.0 * (1.0 - _t_cdf_approx(abs(t_stat), n - 2))
            return (r, p)

        r0 = _pearson(lag0_pairs)
        r1 = _pearson(lag1_pairs)

        if r0 is None and r1 is None:
            continue

        result = {
            "name": name,
            "emoji": emoji,
            "same_day": {
                "r": round(r0[0], 3) if r0 else None,
                "p_value": round(r0[1], 4) if r0 else None,
                "data_points": len(lag0_pairs),
            },
            "next_day": {
                "r": round(r1[0], 3) if r1 else None,
                "p_value": round(r1[1], 4) if r1 else None,
                "data_points": len(lag1_pairs),
            },
        }

        # Determine if delayed effect is stronger
        if r0 and r1:
            if abs(r1[0]) > abs(r0[0]) + 0.1:
                result["effect_timing"] = "delayed"
            elif abs(r0[0]) > abs(r1[0]) + 0.1:
                result["effect_timing"] = "immediate"
            else:
                result["effect_timing"] = "both"
        elif r1 and not r0:
            result["effect_timing"] = "delayed"
        else:
            result["effect_timing"] = "immediate"

        results.append(result)

    # Sort by strongest next-day effect
    results.sort(
        key=lambda x: abs(x["next_day"]["r"] or 0),
        reverse=True,
    )

    # Build description
    delayed = [r for r in results if r["effect_timing"] == "delayed" and r["next_day"]["r"]]
    if delayed:
        top = delayed[0]
        same_r = top["same_day"]["r"]
        same_r_str = f"{same_r:.2f}" if same_r is not None else "N/A"
        desc_text = (
            f"'{top['name']}' has a stronger NEXT-DAY effect on mood "
            f"(lag-1 r={top['next_day']['r']:.2f}) than same-day "
            f"(r={same_r_str}). "
            f"The benefit is delayed."
        )
    elif results:
        top = results[0]
        if top["next_day"]["r"] and abs(top["next_day"]["r"]) > 0.2:
            desc_text = (
                f"'{top['name']}' shows a next-day mood effect "
                f"(r={top['next_day']['r']:.2f})."
            )
        else:
            desc_text = "No strong delayed effects detected yet. Need more data."
    else:
        desc_text = "Not enough data for lag analysis."

    return {"factors": results, "description": desc_text}


def compute_streak_mood_correlations(
    entries, habits, completed_set,
) -> dict:
    """Correlate habit streak length with mood valence.

    For each habit, reconstructs the running streak on each day
    (consecutive days completed), then computes Pearson r between
    streak length and daily mood. A positive r means longer streaks
    predict better mood — the compounding effect of consistency.
    """
    if not habits or not entries:
        return {"habits": [], "description": "No habit or mood data to analyze."}

    # Build daily mood averages
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    daily_mood: dict[date, float] = {
        d: sum(vs) / len(vs) for d, vs in by_date.items()
    }

    if not daily_mood:
        return {"habits": [], "description": "No mood data available."}

    # Determine the date range to analyze
    all_dates = sorted(daily_mood.keys())
    if len(all_dates) < 3:
        return {"habits": [], "description": "Need at least 3 days of mood data."}

    date_range = [
        all_dates[0] + timedelta(days=i)
        for i in range((all_dates[-1] - all_dates[0]).days + 1)
    ]

    results = []

    for habit in habits:
        # Build streak series: for each day, what's the running streak?
        streak = 0
        pairs: list[tuple[int, float]] = []  # (streak_length, mood)

        for d in date_range:
            if (habit.id, d) in completed_set:
                streak += 1
            else:
                streak = 0

            # Only pair days where we have mood data
            if d in daily_mood:
                pairs.append((streak, daily_mood[d]))

        if len(pairs) < 5:
            continue

        streaks = [p[0] for p in pairs]
        moods = [p[1] for p in pairs]

        # Need variance in both
        if len(set(streaks)) < 2 or len(set(moods)) < 2:
            continue

        # Max streak observed
        max_streak = max(streaks)
        avg_streak = sum(streaks) / len(streaks)

        # Pearson r
        n = len(pairs)
        sum_x = sum(streaks)
        sum_y = sum(moods)
        sum_xy = sum(s * m for s, m in pairs)
        sum_x2 = sum(s * s for s in streaks)
        sum_y2 = sum(m * m for m in moods)

        numerator = n * sum_xy - sum_x * sum_y
        denom_x = n * sum_x2 - sum_x * sum_x
        denom_y = n * sum_y2 - sum_y * sum_y

        if denom_x <= 0 or denom_y <= 0:
            continue

        r = numerator / math.sqrt(denom_x * denom_y)

        # p-value
        if abs(r) >= 1.0:
            p_value = 0.0
        else:
            t_stat = r * math.sqrt((n - 2) / (1 - r * r))
            df = n - 2
            p_value = 2.0 * (1.0 - _t_cdf_approx(abs(t_stat), df))

        # Strength classification
        abs_r = abs(r)
        if abs_r < 0.2:
            strength = "negligible"
        elif abs_r < 0.4:
            strength = "weak"
        elif abs_r < 0.6:
            strength = "moderate"
        elif abs_r < 0.8:
            strength = "strong"
        else:
            strength = "very_strong"

        results.append({
            "habit_name": habit.name,
            "habit_emoji": habit.emoji,
            "r": round(r, 3),
            "p_value": round(p_value, 4),
            "strength": strength,
            "significant": p_value < 0.05,
            "data_points": n,
            "max_streak": max_streak,
            "avg_streak": round(avg_streak, 1),
            "direction": "positive" if r > 0 else "negative" if r < 0 else "none",
        })

    results.sort(key=lambda x: abs(x["r"]), reverse=True)

    if not results:
        desc_text = "Not enough streak data to analyze yet. Keep logging for a few more days."
    else:
        top = results[0]
        if top["significant"] and top["strength"] not in ("negligible",):
            desc_text = (
                f"Consistency matters: longer '{top['habit_name']}' streaks "
                f"{'correlate with higher' if top['r'] > 0 else 'correlate with lower'} mood "
                f"(r={top['r']:.2f}, longest streak: {top['max_streak']} days)."
            )
        else:
            desc_text = (
                f"No strong streak-mood relationship yet. "
                f"Longest streak: {results[0]['max_streak']} days ({results[0]['habit_name']})."
            )

    return {"habits": results, "description": desc_text}


def _t_cdf_approx(t: float, df: int) -> float:
    """Approximate t-distribution CDF using normal approximation.

    Good enough for df >= 3. For our use (significance testing),
    we just need to know if p < 0.05, not the exact value.
    """
    # Cornish-Fisher approximation for t → z
    if df <= 0:
        return 0.5
    g1 = (t * t + 1) / (4 * df)
    z = t * (1 - g1)

    # Standard normal CDF approximation (Abramowitz & Stegun)
    if z < 0:
        return 1.0 - _t_cdf_approx(-t, df)

    b0 = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429

    t_val = 1.0 / (1.0 + b0 * z)
    phi = math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi)
    return 1.0 - phi * (b1 * t_val + b2 * t_val**2 + b3 * t_val**3
                        + b4 * t_val**4 + b5 * t_val**5)


def compute_volatility(entries, window: int = 7) -> dict:
    """Rolling standard deviation of daily mood averages.

    High volatility = mood swings. Low = emotional stability.
    Compares current window vs previous window.
    """
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    sorted_dates = sorted(by_date.keys())
    daily_avgs = [sum(by_date[d]) / len(by_date[d]) for d in sorted_dates]

    if len(daily_avgs) < 3:
        return {"current_volatility": None, "direction": "insufficient_data",
                "description": "Need more data to measure mood stability."}

    def _std(values):
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    current_std = _std(daily_avgs[-window:])

    # Compare to previous window if available
    if len(daily_avgs) >= window * 2:
        prev_std = _std(daily_avgs[-window * 2:-window])
        change = current_std - prev_std

        if abs(change) < 0.1:
            direction = "stable"
            desc_text = "Your mood variability has been consistent."
        elif change > 0:
            direction = "increasing"
            desc_text = "Your mood has been more variable recently than the prior week."
        else:
            direction = "decreasing"
            desc_text = "Your mood has been more steady recently compared to the prior week."
    else:
        prev_std = None
        change = None
        direction = "baseline"
        desc_text = "Building a baseline for mood stability measurement."

    # Classify absolute level
    if current_std < 0.5:
        level = "low"
    elif current_std < 1.5:
        level = "moderate"
    else:
        level = "high"

    return {
        "current_volatility": round(current_std, 2),
        "previous_volatility": round(prev_std, 2) if prev_std is not None else None,
        "change": round(change, 2) if change is not None else None,
        "direction": direction,
        "level": level,
        "description": desc_text,
    }


def compute_meditation_effectiveness(med_sessions) -> dict:
    """Average mood change from before to after meditation.

    Positive delta = mood tends to improve after meditating.
    """
    if not med_sessions:
        return {"avg_delta": None, "sessions_analyzed": 0,
                "description": "No meditation sessions with before/after mood data."}

    deltas = []
    for s in med_sessions:
        before = valence(s.mood_before)
        after = valence(s.mood_after)
        if before is not None and after is not None:
            deltas.append(after - before)

    if not deltas:
        return {"avg_delta": None, "sessions_analyzed": 0,
                "description": "No sessions with valid mood comparisons."}

    avg_delta = sum(deltas) / len(deltas)
    improved = sum(1 for d in deltas if d > 0)
    unchanged = sum(1 for d in deltas if d == 0)
    worsened = sum(1 for d in deltas if d < 0)

    if avg_delta > 0.3:
        desc_text = (
            f"Meditation tends to shift your mood positively "
            f"(+{avg_delta:.1f} avg). {improved}/{len(deltas)} sessions "
            f"showed improvement."
        )
    elif avg_delta < -0.3:
        desc_text = (
            f"Meditation sessions have been followed by lower mood scores "
            f"on average — this may reflect deeper processing rather than "
            f"a negative outcome."
        )
    else:
        desc_text = "Meditation has a neutral effect on your mood scores so far."

    return {
        "avg_delta": round(avg_delta, 2),
        "sessions_analyzed": len(deltas),
        "improved": improved,
        "unchanged": unchanged,
        "worsened": worsened,
        "description": desc_text,
    }


# ── ARIMA Forecast ───────────────────────────────────────────────────

MIN_ARIMA_ENTRIES = 7  # minimum mood entries required


def _test_stationarity(daily_avgs: list[float]) -> dict:
    """Augmented Dickey-Fuller test for stationarity.

    ADF tests whether a time series has a unit root (is non-stationary).
    - p-value < 0.05 → data IS stationary (no differencing needed, d=0)
    - p-value >= 0.05 → data is NOT stationary (needs differencing, d>=1)

    Returns test results including recommended d value.
    """
    from statsmodels.tsa.stattools import adfuller

    # Test raw data
    result = adfuller(daily_avgs, autolag="AIC")
    raw_p = result[1]
    raw_stationary = raw_p < 0.05

    # If not stationary, test first difference
    if not raw_stationary and len(daily_avgs) > 3:
        diffs = [daily_avgs[i] - daily_avgs[i - 1] for i in range(1, len(daily_avgs))]
        diff_result = adfuller(diffs, autolag="AIC")
        diff_p = diff_result[1]
        diff_stationary = diff_p < 0.05
    else:
        diff_p = None
        diff_stationary = None

    # Recommend d value
    if raw_stationary:
        recommended_d = 0
    elif diff_stationary:
        recommended_d = 1
    else:
        recommended_d = 1  # default — d=2 is rare and risky

    return {
        "raw_p_value": round(raw_p, 4),
        "raw_stationary": raw_stationary,
        "diff_p_value": round(diff_p, 4) if diff_p is not None else None,
        "diff_stationary": diff_stationary,
        "recommended_d": recommended_d,
    }


def _select_arima_order(daily_avgs: list[float]) -> tuple[tuple[int, int, int], dict]:
    """Select best ARIMA(p,d,q) order using ADF + AIC.

    Step 1: ADF test determines d (differencing order).
    Step 2: AIC grid search over p and q candidates with fixed d.
    Returns (best_order, stationarity_info).
    """
    import warnings

    from statsmodels.tsa.arima.model import ARIMA

    # Step 1: Determine d via ADF test
    stationarity = _test_stationarity(daily_avgs)
    d = stationarity["recommended_d"]

    # Step 2: Grid search p and q with ADF-determined d
    candidates = []
    for p in range(0, 4):
        for q in range(0, 3):
            if p == 0 and q == 0:
                continue  # (0,d,0) is meaningless
            candidates.append((p, d, q))

    best_aic = float("inf")
    best_order = (1, d, 1)  # safe default with ADF-chosen d

    for order in candidates:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = ARIMA(daily_avgs, order=order)
                fitted = model.fit()
                if fitted.aic < best_aic:
                    best_aic = fitted.aic
                    best_order = order
        except Exception:
            continue

    return best_order, stationarity


def compute_arima_forecast(entries) -> dict:
    """Next-day and 7-day mood forecast using ARIMA(1,1,1).

    Unlike EWMA (weighted average of recent values), ARIMA models the
    *structure* in the time series: autoregression on past values,
    differencing to remove trend, and error correction from past misses.

    Requires at least 7 mood entries to produce a result.
    """
    if len(entries) < MIN_ARIMA_ENTRIES:
        remaining = MIN_ARIMA_ENTRIES - len(entries)
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "insufficient_data",
            "description": (
                f"Need {remaining} more mood entr{'y' if remaining == 1 else 'ies'} "
                f"to generate an ARIMA forecast (minimum {MIN_ARIMA_ENTRIES})."
            ),
            "method": "arima",
        }

    # Build daily average valence series
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    sorted_dates = sorted(by_date.keys())
    if len(sorted_dates) < MIN_ARIMA_ENTRIES:
        remaining = MIN_ARIMA_ENTRIES - len(sorted_dates)
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "insufficient_data",
            "description": (
                f"Need mood data on {remaining} more day{'s' if remaining != 1 else ''} "
                f"to generate an ARIMA forecast (minimum {MIN_ARIMA_ENTRIES} days)."
            ),
            "method": "arima",
        }

    daily_avgs = [sum(by_date[d]) / len(by_date[d]) for d in sorted_dates]

    # Auto-select best ARIMA order via AIC, then fit and forecast
    try:
        import warnings
        from statsmodels.tsa.arima.model import ARIMA

        order, stationarity = _select_arima_order(daily_avgs)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ARIMA(daily_avgs, order=order)
            fitted = model.fit()

        # Forecast next 7 days
        raw_forecast = fitted.forecast(steps=7)

        # Clamp all predictions to valid valence range [-3, +3]
        clamped = [max(-3.0, min(3.0, float(v))) for v in raw_forecast]

        next_day_val = clamped[0]
        next_day_label = _valence_to_label(next_day_val)

        # Build 7-day forecast with dates and labels
        tomorrow = date.today() + timedelta(days=1)
        seven_day = []
        for i, val in enumerate(clamped):
            forecast_date = tomorrow + timedelta(days=i)
            seven_day.append({
                "date": forecast_date.isoformat(),
                "day": forecast_date.strftime("%A"),
                "forecast_valence": round(val, 2),
                "forecast_label": _valence_to_label(val),
            })

        # Confidence based on data volume
        if len(sorted_dates) >= 30:
            confidence = "high"
        elif len(sorted_dates) >= 14:
            confidence = "moderate"
        else:
            confidence = "low"

        return {
            "next_day": {
                "date": tomorrow.isoformat(),
                "forecast_valence": round(next_day_val, 2),
                "forecast_label": next_day_label,
            },
            "next_7_days": seven_day,
            "confidence": confidence,
            "data_days": len(sorted_dates),
            "model_order": list(order),
            "aic": round(fitted.aic, 2),
            "stationarity": stationarity,
            "description": (
                f"ARIMA{order} predicts tomorrow may feel around "
                f"'{next_day_label}' territory."
            ),
            "method": "arima",
        }

    except Exception:
        # Fallback if ARIMA fitting fails (can happen with constant data
        # or very short series where differencing leaves nothing)
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "error",
            "description": (
                "ARIMA model could not converge on this data. "
                "This usually means mood values are too constant — "
                "more varied data will help."
            ),
            "method": "arima",
        }


# ── ARIMAX Forecast (multivariate) ───────────────────────────────────


def _build_exogenous_matrix(
    sorted_dates: list[date],
    habits,
    completed_set: set,
    med_sessions,
    journal_dates: set[date],
) -> list[list[float]]:
    """Build a matrix of external factors aligned to the mood date series.

    Each row = one day. Columns = exogenous variables:
      [habit_1_done, habit_2_done, ..., meditated, journaled]

    Values are 0.0 or 1.0 (binary: did it or didn't).
    Designed to be pluggable — adding a new studio's data means
    adding another column here.
    """
    # Map habit completions by date
    habit_ids = [h.id for h in habits] if habits else []

    rows = []
    for d in sorted_dates:
        row = []
        # One column per habit (did they complete it that day?)
        for hid in habit_ids:
            row.append(1.0 if (hid, d) in completed_set else 0.0)

        # Did they meditate that day?
        med_dates = set()
        for s in med_sessions:
            md = _to_date(s.created_at)
            med_dates.add(md)
        row.append(1.0 if d in med_dates else 0.0)

        # Did they journal that day?
        row.append(1.0 if d in journal_dates else 0.0)

        rows.append(row)

    return rows


def _get_exog_labels(habits, has_meditation: bool, has_journal: bool) -> list[str]:
    """Human-readable labels for each exogenous column."""
    labels = [h.name for h in habits] if habits else []
    if has_meditation:
        labels.append("meditation")
    if has_journal:
        labels.append("journaling")
    return labels


async def _fetch_journal_dates(session, user_id: str, days: int) -> set[date]:
    """Fetch dates when user wrote journal entries."""
    JournalEntry = sys.modules["zugalife.journal.models"].JournalEntry
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(JournalEntry.created_at)
        .where(JournalEntry.user_id == user_id, JournalEntry.created_at >= since)
    )
    return {_to_date(row.created_at) for row in result.all()}


def compute_arimax_forecast(
    entries, habits, completed_set, med_sessions, journal_dates: set[date],
) -> dict:
    """Next-day and 7-day forecast using ARIMAX — ARIMA with external factors.

    Unlike plain ARIMA (mood-only), ARIMAX includes habit completions,
    meditation, and journaling as predictive inputs. This models the
    CPP → CQA relationship: external behaviors (inputs) influence
    mood outcomes (output).

    Requires at least 7 days of mood data. Falls back to plain ARIMA
    if there are no exogenous variables or they have zero variance.
    """
    if len(entries) < MIN_ARIMA_ENTRIES:
        remaining = MIN_ARIMA_ENTRIES - len(entries)
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "insufficient_data",
            "exogenous_factors": [],
            "description": (
                f"Need {remaining} more mood entr{'y' if remaining == 1 else 'ies'} "
                f"to generate an ARIMAX forecast (minimum {MIN_ARIMA_ENTRIES})."
            ),
            "method": "arimax",
        }

    # Build daily average valence series
    by_date: dict[date, list[int]] = defaultdict(list)
    for entry in entries:
        v = valence(entry.label)
        if v is not None:
            by_date[_to_date(entry.created_at)].append(v)

    sorted_dates = sorted(by_date.keys())
    if len(sorted_dates) < MIN_ARIMA_ENTRIES:
        remaining = MIN_ARIMA_ENTRIES - len(sorted_dates)
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "insufficient_data",
            "exogenous_factors": [],
            "description": (
                f"Need mood data on {remaining} more day{'s' if remaining != 1 else ''} "
                f"to generate an ARIMAX forecast (minimum {MIN_ARIMA_ENTRIES} days)."
            ),
            "method": "arimax",
        }

    daily_avgs = [sum(by_date[d]) / len(by_date[d]) for d in sorted_dates]

    # Build exogenous matrix
    exog_matrix = _build_exogenous_matrix(
        sorted_dates, habits, completed_set, med_sessions, journal_dates,
    )
    exog_labels = _get_exog_labels(
        habits, has_meditation=True, has_journal=True,
    )

    # Check if we have any useful exogenous data (need variance in at least one column)
    has_useful_exog = False
    if exog_matrix and exog_matrix[0]:
        for col_idx in range(len(exog_matrix[0])):
            col_vals = [row[col_idx] for row in exog_matrix]
            if len(set(col_vals)) > 1:  # has variance
                has_useful_exog = True
                break

    try:
        import warnings
        import numpy as np
        from statsmodels.tsa.arima.model import ARIMA

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            if has_useful_exog:
                exog_array = np.array(exog_matrix)

                # Remove columns with zero variance (ARIMA can't use them)
                useful_cols = []
                useful_labels = []
                for i in range(exog_array.shape[1]):
                    if np.std(exog_array[:, i]) > 0:
                        useful_cols.append(i)
                        if i < len(exog_labels):
                            useful_labels.append(exog_labels[i])

                exog_filtered = exog_array[:, useful_cols]

                order, stationarity = _select_arima_order(daily_avgs)
                model = ARIMA(daily_avgs, exog=exog_filtered, order=order)
                fitted = model.fit()

                # For forecasting, assume habits/meditation/journal continue
                # at their recent rate (last 7 days average)
                recent_window = min(7, len(exog_filtered))
                future_exog = np.tile(
                    exog_filtered[-recent_window:].mean(axis=0), (7, 1)
                )

                raw_forecast = fitted.forecast(steps=7, exog=future_exog)
                method = "arimax"
                used_factors = useful_labels
                selected_order = order
            else:
                # Fall back to plain ARIMA
                order, stationarity = _select_arima_order(daily_avgs)
                model = ARIMA(daily_avgs, order=order)
                fitted = model.fit()
                selected_order = order
                raw_forecast = fitted.forecast(steps=7)
                method = "arima_fallback"
                used_factors = []

        # Clamp to valid valence range
        clamped = [max(-3.0, min(3.0, float(v))) for v in raw_forecast]

        next_day_val = clamped[0]
        next_day_label = _valence_to_label(next_day_val)

        # Build 7-day forecast
        tomorrow = date.today() + timedelta(days=1)
        seven_day = []
        for i, val in enumerate(clamped):
            forecast_date = tomorrow + timedelta(days=i)
            seven_day.append({
                "date": forecast_date.isoformat(),
                "day": forecast_date.strftime("%A"),
                "forecast_valence": round(val, 2),
                "forecast_label": _valence_to_label(val),
            })

        # Confidence
        if len(sorted_dates) >= 30 and has_useful_exog:
            confidence = "high"
        elif len(sorted_dates) >= 14:
            confidence = "moderate"
        else:
            confidence = "low"

        description = (
            f"ARIMAX{selected_order} predicts tomorrow may feel around "
            f"'{next_day_label}' territory"
        )
        if used_factors:
            description += f", factoring in: {', '.join(used_factors)}"
        description += "."

        return {
            "next_day": {
                "date": tomorrow.isoformat(),
                "forecast_valence": round(next_day_val, 2),
                "forecast_label": next_day_label,
            },
            "next_7_days": seven_day,
            "confidence": confidence,
            "data_days": len(sorted_dates),
            "model_order": list(selected_order),
            "aic": round(fitted.aic, 2),
            "exogenous_factors": used_factors,
            "description": description,
            "method": method,
        }

    except Exception:
        return {
            "next_day": None,
            "next_7_days": [],
            "confidence": "error",
            "exogenous_factors": [],
            "description": (
                "ARIMAX model could not converge. Falling back to "
                "standard ARIMA may work better with current data."
            ),
            "method": "arimax",
        }


# ── Orchestrator ─────────────────────────────────────────────────────

async def compute_all(session, user_id: str, days: int = 30) -> dict:
    """Run all analytics and return combined results."""
    days = min(max(days, 1), 365)  # defensive clamp
    entries = await _fetch_mood_entries(session, user_id, days)
    habits, completed_set, amount_map = await _fetch_habit_completions(session, user_id, days)
    med_sessions = await _fetch_meditation_moods(session, user_id, days)
    med_sessions_full = await _fetch_meditation_sessions_full(session, user_id, days)
    journal_dates = await _fetch_journal_dates(session, user_id, days)
    therapist_dates = await _fetch_therapist_dates(session, user_id, days)

    return {
        "period_days": days,
        "total_entries": len(entries),
        "trend": compute_trend(entries, days),
        "day_of_week": compute_day_of_week(entries),
        "forecast": compute_forecast(entries),
        "habit_correlations": compute_habit_correlations(entries, habits, completed_set),
        "habit_amount_correlations": compute_habit_amount_correlations(entries, habits, amount_map),
        "streak_correlations": compute_streak_mood_correlations(entries, habits, completed_set),
        "engagement_correlations": compute_engagement_correlations(entries, journal_dates, therapist_dates),
        "lagged_correlations": compute_lagged_correlations(entries, habits, completed_set, med_sessions, journal_dates),
        "interaction_effects": compute_interaction_effects(entries, habits, completed_set, med_sessions, journal_dates),
        "volatility": compute_volatility(entries),
        "meditation_effectiveness": compute_meditation_effectiveness(med_sessions),
        "meditation_type_breakdown": compute_meditation_type_breakdown(med_sessions_full),
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _valence_to_label(score: float) -> str:
    """Map a numeric valence back to the nearest mood label."""
    closest = None
    closest_dist = float("inf")
    for label, val in MOOD_VALENCE.items():
        dist = abs(val - score)
        if dist < closest_dist:
            closest_dist = dist
            closest = label
    return closest
