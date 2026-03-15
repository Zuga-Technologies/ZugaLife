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

    # Get active habits
    habits_result = await session.execute(
        select(HabitDefinition.id, HabitDefinition.name, HabitDefinition.emoji)
        .where(HabitDefinition.user_id == user_id, HabitDefinition.is_active == True)
    )
    habits = habits_result.all()

    # Get completed logs
    logs_result = await session.execute(
        select(HabitLog.habit_id, HabitLog.log_date)
        .where(
            HabitLog.user_id == user_id,
            HabitLog.log_date >= since,
            HabitLog.completed == True,
        )
    )
    logs = logs_result.all()

    # Build a set of (habit_id, date) pairs for quick lookup
    completed_set = {(log.habit_id, log.log_date) for log in logs}

    return habits, completed_set


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

    # Fit ARIMA(1,1,1) — suppress convergence warnings for small datasets
    try:
        import warnings
        from statsmodels.tsa.arima.model import ARIMA

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ARIMA(daily_avgs, order=(1, 1, 1))
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
            "description": (
                f"ARIMA predicts tomorrow may feel around "
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

                model = ARIMA(daily_avgs, exog=exog_filtered, order=(1, 1, 1))
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
            else:
                # Fall back to plain ARIMA
                model = ARIMA(daily_avgs, order=(1, 1, 1))
                fitted = model.fit()
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
            f"ARIMAX predicts tomorrow may feel around "
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
    """Run all 6 analyses and return combined results."""
    days = min(max(days, 1), 365)  # defensive clamp
    entries = await _fetch_mood_entries(session, user_id, days)
    habits, completed_set = await _fetch_habit_completions(session, user_id, days)
    med_sessions = await _fetch_meditation_moods(session, user_id, days)

    return {
        "period_days": days,
        "total_entries": len(entries),
        "trend": compute_trend(entries, days),
        "day_of_week": compute_day_of_week(entries),
        "forecast": compute_forecast(entries),
        "habit_correlations": compute_habit_correlations(entries, habits, completed_set),
        "volatility": compute_volatility(entries),
        "meditation_effectiveness": compute_meditation_effectiveness(med_sessions),
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
