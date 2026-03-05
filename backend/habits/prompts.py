"""ZugaLife habit insight AI prompt builder.

Builds prompts that correlate 7 days of habit data with mood data
to find data-backed patterns. Uses XML tag isolation for prompt
injection defense (Anthropic recommended pattern).
"""

# Mood emoji lookup (reuses same mapping as mood schemas)
_EMOJI_LABELS: dict[str, str] = {
    "\U0001f60a": "Happy", "\U0001f622": "Sad", "\U0001f620": "Angry",
    "\U0001f630": "Anxious", "\U0001f634": "Tired", "\U0001f929": "Excited",
    "\U0001f610": "Neutral", "\U0001f970": "Loved", "\U0001f624": "Frustrated",
    "\U0001f914": "Thoughtful", "\U0001f60c": "Calm", "\U0001f4aa": "Motivated",
}

INSIGHT_COOLDOWN_DAYS = 7


def build_insight_prompt(
    habit_data: str,
    mood_data: str,
    previous_insights: list[str] | None = None,
) -> str:
    """Build the AI habit insight prompt with XML tag isolation.

    Args:
        habit_data: Formatted string of 7 days of habit check-in data.
        mood_data: Formatted string of 7 days of mood log data.
        previous_insights: Past insight summaries to avoid repeating themes.
    """
    anti_repetition = ""
    if previous_insights:
        themes = "\n".join(f"- {ins[:300]}" for ins in previous_insights[-3:])
        anti_repetition = (
            "\n\nPrevious insights (do NOT repeat these themes or observations):\n"
            f"{themes}"
        )

    return f"""You are ZugaLife's habit pattern analyst. Your job is to find data-backed correlations between daily habits and emotional patterns.

Rules:
- Only make observations that are supported by the data below
- Be specific with numbers: "You logged Happy on 4 of 5 days you exercised" not "exercise seems to help"
- If there isn't enough data for a meaningful correlation, say so honestly
- Keep your response to 3-4 short paragraphs maximum
- No generic wellness advice — only data-backed observations from THIS user's data
- Write conversationally in second person ("you")
- Mood data comes from journal entries (some manually tagged, some AI-inferred)
- If a journal entry has mood + text, use both for richer context
- Never be sycophantic — be direct and honest{anti_repetition}

<habit_data>
{habit_data}
</habit_data>

<mood_data>
{mood_data}
</mood_data>

Analyze the correlation between these habits and moods. What patterns do you see?"""


def format_habit_data(
    days: list[dict],
) -> str:
    """Format habit log data into a readable string for the prompt.

    Args:
        days: List of dicts like:
            {"date": "2026-03-01", "habits": [
                {"name": "Sleep", "emoji": "...", "completed": True, "amount": 7.5, "unit": "hours"},
                ...
            ]}
    """
    if not days:
        return "No habit data available for this period."

    lines = []
    for day in days:
        day_line = f"{day['date']}:"
        if not day["habits"]:
            day_line += " (no habits logged)"
        else:
            parts = []
            for h in day["habits"]:
                if h.get("amount") and h.get("unit"):
                    parts.append(f"{h['emoji']} {h['name']}: {h['amount']} {h['unit']}")
                elif h.get("completed"):
                    parts.append(f"{h['emoji']} {h['name']}: done")
            day_line += " " + ", ".join(parts) if parts else " (no habits logged)"
        lines.append(day_line)
    return "\n".join(lines)


def format_mood_data(
    entries: list[dict],
) -> str:
    """Format mood entries into a readable string for the prompt.

    Args:
        entries: List of dicts like:
            {"date": "2026-03-01", "emoji": "😊", "label": "Happy", "note": "..."}
    """
    if not entries:
        return "No mood data available for this period."

    lines = []
    for e in entries:
        line = f"{e['date']}: {e['emoji']} {e['label']}"
        if e.get("note"):
            # Truncate notes to prevent token waste
            note = e["note"][:200]
            line += f' — "{note}"'
        lines.append(line)
    return "\n".join(lines)
