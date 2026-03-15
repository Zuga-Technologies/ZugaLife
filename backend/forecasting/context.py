"""Build therapist-readable mood forecast context.

This module translates forecasting engine output into a natural-language
summary that the therapist can use as context. Data flows ONE WAY into
the therapist module — therapist notes never flow back here.

Language is clinical-neutral throughout.
"""

from __future__ import annotations

import sys

from core.database.session import get_session


async def build_forecast_context(user_id: str) -> str | None:
    """Generate a therapist-readable summary of mood patterns.

    Returns None if insufficient data. The therapist system prompt
    prepends this to its context alongside other ZugaLife data.
    """
    _engine = sys.modules["zugalife.forecasting.engine"]

    async with get_session() as session:
        data = await _engine.compute_all(session, user_id, days=30)

    if data["total_entries"] < 3:
        return None

    sections = []

    # Trend
    trend = data["trend"]
    if trend["direction"] != "insufficient_data":
        sections.append(f"Mood trend (30 days): {trend['description']}")
        if trend.get("avg_valence") is not None:
            sections.append(f"  Average valence: {trend['avg_valence']}/3.0")

    # Day-of-week patterns
    dow = data["day_of_week"]
    days_with_data = [d for d in dow["days"] if d["avg_valence"] is not None]
    if len(days_with_data) >= 3:
        sections.append(f"Weekly pattern: {dow['description']}")

    # Habit correlations
    habits = data["habit_correlations"]
    if habits["habits"]:
        top_positive = [h for h in habits["habits"] if h["delta"] > 0.3]
        if top_positive:
            names = ", ".join(h["habit_name"] for h in top_positive[:3])
            sections.append(f"Positive mood correlations with: {names}")

    # Volatility
    vol = data["volatility"]
    if vol["current_volatility"] is not None:
        sections.append(
            f"Mood stability: {vol['level']} variability "
            f"(std dev {vol['current_volatility']}). {vol['description']}"
        )

    # Meditation effectiveness
    med = data["meditation_effectiveness"]
    if med["sessions_analyzed"] > 0:
        sections.append(f"Meditation effect: {med['description']}")

    # ARIMA forecast (separate from EWMA — models structural patterns)
    try:
        async with get_session() as session:
            entries = await _engine._fetch_mood_entries(session, user_id, days=30)
        arima = _engine.compute_arima_forecast(entries)

        if arima["next_day"] is not None:
            day1 = arima["next_day"]
            sections.append(
                f"ARIMA forecast: tomorrow likely around "
                f"'{day1['forecast_label']}' ({day1['forecast_valence']:+.1f}), "
                f"confidence: {arima['confidence']}"
            )

            # Flag divergence between EWMA and ARIMA if both available
            ewma = data["forecast"]
            if ewma.get("forecast_valence") is not None:
                gap = abs(day1["forecast_valence"] - ewma["forecast_valence"])
                if gap > 1.0:
                    sections.append(
                        f"Note: EWMA and ARIMA forecasts diverge by {gap:.1f} points "
                        f"— mood pattern may be shifting."
                    )

            # 7-day outlook summary
            week = arima["next_7_days"]
            if len(week) >= 7:
                labels = [d["forecast_label"] for d in week]
                unique = set(labels)
                if len(unique) == 1:
                    sections.append(f"7-day ARIMA outlook: steady around '{labels[0]}'")
                else:
                    sections.append(
                        f"7-day ARIMA outlook: ranges from "
                        f"'{week[0]['forecast_label']}' to '{week[-1]['forecast_label']}'"
                    )
    except Exception:
        pass  # ARIMA is optional — don't break therapist if it fails

    if not sections:
        return None

    return "Mood analytics (statistical, last 30 days):\n  " + "\n  ".join(sections)
