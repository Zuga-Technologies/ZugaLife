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

    if not sections:
        return None

    return "Mood analytics (statistical, last 30 days):\n  " + "\n  ".join(sections)
