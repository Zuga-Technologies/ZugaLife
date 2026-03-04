"""ZugaLife AI reflection prompt builder.

Builds prompts for the AI to generate follow-up questions — NOT advice.
The AI acts as an honest mirror, not a therapist.
"""

# Mood emoji lookup (reuses the same mapping from mood schemas)
_EMOJI_LABELS: dict[str, str] = {
    "\U0001f60a": "Happy", "\U0001f622": "Sad", "\U0001f620": "Angry",
    "\U0001f630": "Anxious", "\U0001f634": "Tired", "\U0001f929": "Excited",
    "\U0001f610": "Neutral", "\U0001f970": "Loved", "\U0001f624": "Frustrated",
    "\U0001f914": "Thoughtful", "\U0001f60c": "Calm", "\U0001f4aa": "Motivated",
}

MAX_REFLECTIONS_PER_ENTRY = 3


def build_reflection_prompt(
    journal_content: str,
    title: str | None = None,
    mood_emoji: str | None = None,
    previous_reflections: list[str] | None = None,
) -> str:
    """Build the AI reflection prompt with prompt injection isolation.

    The journal content is wrapped in XML tags for isolation — this is
    Anthropic's recommended pattern for separating user content from
    instructions. The AI cannot break out of this context.
    """
    mood_context = ""
    if mood_emoji:
        label = _EMOJI_LABELS.get(mood_emoji, "")
        if label:
            mood_context = f"\nThe person tagged this entry with a {label} mood ({mood_emoji})."

    title_context = ""
    if title:
        title_context = f"\n<entry_title>{title}</entry_title>"

    anti_repetition = ""
    if previous_reflections:
        themes = "\n".join(f"- {r[:200]}" for r in previous_reflections)
        anti_repetition = (
            "\n\nPrevious reflections on this entry (do NOT repeat these themes):\n"
            f"{themes}"
        )

    return f"""You are a reflective journal companion. Your job is to ask follow-up questions that help the person think more deeply — NOT to give advice, NOT to praise, NOT to diagnose.

Rules:
- Ask 1-2 genuine follow-up questions
- Be direct and honest — no sycophantic praise like "great insight!" or "that's wonderful!"
- Keep your response to 2-3 short paragraphs maximum
- Write conversationally in second person ("you")
- If there's a mood tag, acknowledge it naturally (don't force it)
- Never give advice, therapy, or diagnoses
- Never say "I'm glad you shared this" or similar empty validation{anti_repetition}
{mood_context}{title_context}

<journal_entry>
{journal_content}
</journal_entry>

Respond with your reflection questions now."""
