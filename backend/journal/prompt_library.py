"""ZugaLife journal prompt library — rotating guided prompts based on psychological research.

Pennebaker's expressive writing research (30+ years): the therapeutic ingredient is
emotional engagement, not factual recall. Writing about feelings produces measurable
health outcomes; writing about facts alone produces none.

Gratitude journaling (Emmons & McCullough): 2-3x per week is optimal.
Daily gratitude habituates and loses emotional impact.

Prompt rotation: deterministic per user per day (hash-seeded) to ensure consistency
while mixing expressive, gratitude, and reflective prompts across the week.
"""

import hashlib
from datetime import date

# ---------------------------------------------------------------------------
# Prompt library by category
# ---------------------------------------------------------------------------

EXPRESSIVE_PROMPTS = [
    {
        "title": "Name the feeling",
        "prompt": "What emotion surprised you today? Don't explain it yet \u2014 just name it and sit with it for a moment.",
        "category": "expressive",
    },
    {
        "title": "What's weighing on you",
        "prompt": "Describe something that's been on your mind. Focus on how it makes you feel, not just what happened.",
        "category": "expressive",
    },
    {
        "title": "The unsent letter",
        "prompt": "Write something you wish you could say to someone but haven't. You don't have to send it.",
        "category": "expressive",
    },
    {
        "title": "Before and after",
        "prompt": "Think of a moment today that changed your mood. What were you feeling before, and what shifted?",
        "category": "expressive",
    },
    {
        "title": "The quiet thing",
        "prompt": "What's something you've been avoiding thinking about? Write it down \u2014 even a few words helps.",
        "category": "expressive",
    },
    {
        "title": "Body check-in",
        "prompt": "Where in your body are you holding tension right now? Describe what it feels like \u2014 not why, just what.",
        "category": "expressive",
    },
]

GRATITUDE_PROMPTS = [
    {
        "title": "Three good things",
        "prompt": "Name 3 things you're grateful for today. At least one should be something small you almost missed.",
        "category": "gratitude",
    },
    {
        "title": "Someone who helped",
        "prompt": "Who made your day a little better today, and how? They don't have to know.",
        "category": "gratitude",
    },
    {
        "title": "What went right",
        "prompt": "What's one thing that went well recently \u2014 and what was your part in making it happen?",
        "category": "gratitude",
    },
    {
        "title": "The simple pleasure",
        "prompt": "Describe a small moment of comfort or pleasure today. A meal, a sound, a view, a feeling.",
        "category": "gratitude",
    },
]

REFLECTION_PROMPTS = [
    {
        "title": "Letter to yesterday",
        "prompt": "What would you tell yesterday's version of yourself? What do you know now that you didn't then?",
        "category": "reflection",
    },
    {
        "title": "The pattern",
        "prompt": "Is there a pattern you've noticed in your recent days \u2014 something that keeps coming up?",
        "category": "reflection",
    },
    {
        "title": "Future self check-in",
        "prompt": "Imagine yourself 6 months from now. What would that version of you say about how you're spending today?",
        "category": "reflection",
    },
    {
        "title": "What you're learning",
        "prompt": "What's one thing you're learning about yourself right now \u2014 something you couldn't have said a month ago?",
        "category": "reflection",
    },
    {
        "title": "Energy audit",
        "prompt": "What gave you energy this week? What drained it? Write freely about both.",
        "category": "reflection",
    },
]

# Combined pool
ALL_PROMPTS = EXPRESSIVE_PROMPTS + GRATITUDE_PROMPTS + REFLECTION_PROMPTS

# Weekly schedule: which category for each day of week (Mon=0..Sun=6)
# Expressive 3x, Gratitude 2x, Reflection 2x — per Pennebaker/Emmons research
_DAILY_CATEGORY = [
    "expressive",   # Monday
    "gratitude",    # Tuesday
    "expressive",   # Wednesday
    "reflection",   # Thursday
    "gratitude",    # Friday
    "expressive",   # Saturday
    "reflection",   # Sunday
]

_POOLS = {
    "expressive": EXPRESSIVE_PROMPTS,
    "gratitude": GRATITUDE_PROMPTS,
    "reflection": REFLECTION_PROMPTS,
}


def get_daily_prompt(user_id: str, for_date: date | None = None) -> dict:
    """Get today's journal prompt for a user. Deterministic per user+date.

    Returns: {"title": str, "prompt": str, "category": str}
    """
    if for_date is None:
        for_date = date.today()

    # Determine category from day of week
    category = _DAILY_CATEGORY[for_date.weekday()]
    pool = _POOLS[category]

    # Deterministic selection within category (same user+date = same prompt)
    seed = hashlib.sha256(f"{user_id}:{for_date.isoformat()}:journal".encode()).hexdigest()
    idx = int(seed[:8], 16) % len(pool)

    return pool[idx]
