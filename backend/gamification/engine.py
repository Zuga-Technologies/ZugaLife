"""ZugaLife gamification engine — XP awards, level calculation, badge checks, and daily challenges.

This module contains pure business logic with no FastAPI dependencies.
It is called by routes.py and can also be imported by other ZugaLife modules
(habits, journal, meditation, etc.) to award XP at the point of action.

Usage from another ZugaLife route:
    _gam_engine = sys.modules["zugalife.gamification.engine"]
    result = await _gam_engine.award_xp(
        session, user_id="...", source="habit_check", description="Completed Sleep habit"
    )
"""

import hashlib
import sys
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Static lookup tables
# ---------------------------------------------------------------------------

# XP awarded per source action (base, before streak multiplier)
XP_TABLE: dict[str, int] = {
    "mood_log": 10,
    "habit_check": 15,
    "journal_entry": 25,
    "meditation_complete": 30,
    "therapist_session": 50,
    "goal_milestone": 40,
    "daily_challenge": 25,  # default; individual challenges carry their own xp_reward
    "streak_bonus": 0,       # calculated dynamically: streak_days * 5
}

# Level thresholds — (min total_xp, level_number, level_name)
LEVELS: list[tuple[int, int, str]] = [
    (5500, 10, "Enlightened"),
    (4000, 9, "Master"),
    (3000, 8, "Resilient"),
    (2200, 7, "Mindful"),
    (1500, 6, "Dedicated"),
    (1000, 5, "Achiever"),
    (600, 4, "Practitioner"),
    (300, 3, "Seeker"),
    (100, 2, "Explorer"),
    (0, 1, "Beginner"),
]

# Badge definitions — key → display metadata. NOT stored in DB.
BADGES: dict[str, dict] = {
    "first_mood":       {"title": "Mood Tracker",      "description": "Logged your first mood",                  "emoji": "🎭"},
    "first_journal":    {"title": "Dear Diary",         "description": "Wrote your first journal entry",          "emoji": "📝"},
    "first_meditation": {"title": "Inner Peace",        "description": "Completed your first meditation",         "emoji": "🧘"},
    "first_therapy":    {"title": "Open Mind",          "description": "Had your first therapist session",        "emoji": "💬"},
    "streak_7":         {"title": "Week Warrior",       "description": "7-day activity streak",                   "emoji": "🔥"},
    "streak_30":        {"title": "Monthly Master",     "description": "30-day activity streak",                  "emoji": "⚡"},
    "streak_100":       {"title": "Unstoppable",        "description": "100-day activity streak",                 "emoji": "💎"},
    "all_habits_day":   {"title": "Perfect Day",        "description": "Completed all habits in one day",         "emoji": "⭐"},
    "level_5":          {"title": "Halfway There",      "description": "Reached level 5",                         "emoji": "🏔️"},
    "level_10":         {"title": "Enlightened",        "description": "Reached maximum level",                   "emoji": "👑"},
    "meditation_10":    {"title": "Zen Master",         "description": "Completed 10 meditation sessions",        "emoji": "🪷"},
    "journal_10":       {"title": "Storyteller",        "description": "Wrote 10 journal entries",                "emoji": "📚"},
    "mood_30":          {"title": "Self Aware",         "description": "Logged 30 moods",                         "emoji": "🔮"},
    "goal_complete":    {"title": "Goal Getter",        "description": "Completed your first goal",               "emoji": "🎯"},
    "five_challenges":  {"title": "Challenge Accepted", "description": "Completed 5 daily challenges",            "emoji": "🏆"},
}

# Daily challenge pool — seeded by (user_id + date) for deterministic selection
CHALLENGE_POOL: list[dict] = [
    {"key": "log_mood_2x",        "title": "Double Check-in",   "desc": "Log your mood twice today",                         "xp": 25},
    {"key": "meditate_today",     "title": "Find Your Center",  "desc": "Complete a meditation session",                     "xp": 30},
    {"key": "journal_entry",      "title": "Express Yourself",  "desc": "Write a journal entry",                             "xp": 25},
    {"key": "all_habits",         "title": "Perfect Day",       "desc": "Complete all your habits today",                    "xp": 50},
    {"key": "therapist_session",  "title": "Talk It Out",       "desc": "Have a therapist session",                          "xp": 40},
    {"key": "long_meditation",    "title": "Deep Dive",         "desc": "Complete a 10+ minute meditation",                  "xp": 40},
    {"key": "reflect_journal",    "title": "Mirror Mirror",     "desc": "Get an AI reflection on a journal entry",           "xp": 30},
    {"key": "habit_streak_3",     "title": "Triple Threat",     "desc": "Have 3+ habits with active streaks",                "xp": 35},
]


# ---------------------------------------------------------------------------
# Pure helper functions (no DB access)
# ---------------------------------------------------------------------------

def compute_level(total_xp: int) -> tuple[int, str]:
    """Return (level_number, level_name) for a given total XP."""
    for min_xp, level, name in LEVELS:
        if total_xp >= min_xp:
            return level, name
    return 1, "Beginner"


def xp_for_level(level: int) -> int:
    """Return the total XP threshold to reach a given level."""
    for min_xp, lvl, _ in LEVELS:
        if lvl == level:
            return min_xp
    return 0


def compute_streak_multiplier(streak_days: int) -> float:
    if streak_days >= 30:
        return 2.0
    if streak_days >= 7:
        return 1.5
    return 1.0


def select_daily_challenges(user_id: str, for_date: date) -> list[dict]:
    """Return 3 challenges from the pool, deterministically seeded by user_id + date.

    The seed combines user_id and ISO date so the same user always gets the
    same challenges on the same day, but different users get different picks.
    """
    seed_str = f"{user_id}:{for_date.isoformat()}"
    seed_int = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)

    pool = CHALLENGE_POOL.copy()
    # Fisher-Yates-style shuffle using the deterministic seed
    for i in range(len(pool) - 1, 0, -1):
        j = seed_int % (i + 1)
        pool[i], pool[j] = pool[j], pool[i]
        seed_int //= (i + 1)  # advance the seed without Python's random module

    return pool[:3]


def build_badge_response(badge_key: str, earned_at=None):
    """Build a BadgeResponse dict for a given badge key."""
    _schemas = sys.modules["zugalife.gamification.schemas"]
    meta = BADGES.get(badge_key, {"title": badge_key, "description": "", "emoji": "?"})
    return _schemas.BadgeResponse(
        badge_key=badge_key,
        title=meta["title"],
        description=meta["description"],
        emoji=meta["emoji"],
        earned_at=earned_at,
    )


# ---------------------------------------------------------------------------
# DB-backed helpers
# ---------------------------------------------------------------------------

async def _get_or_create_user_xp(session, user_id: str):
    """Return the UserXP row for user_id, creating one if missing."""
    _models = sys.modules["zugalife.gamification.models"]
    UserXP = _models.UserXP

    result = await session.execute(select(UserXP).where(UserXP.user_id == user_id))
    user_xp = result.scalar_one_or_none()
    if user_xp is None:
        user_xp = UserXP(user_id=user_id)
        session.add(user_xp)
        await session.flush()  # assign id without committing
    return user_xp


async def _check_and_award_badges(session, user_id: str, source: str) -> list:
    """Inspect the user's history and award any newly earned badges.

    Returns a list of BadgeResponse objects for badges earned in this call.
    """
    _models = sys.modules["zugalife.gamification.models"]
    UserXP = _models.UserXP
    UserBadge = _models.UserBadge
    XPTransaction = _models.XPTransaction

    # Fetch existing badges so we can skip ones already earned
    existing_result = await session.execute(
        select(UserBadge.badge_key).where(UserBadge.user_id == user_id)
    )
    existing = {row[0] for row in existing_result.all()}

    user_xp_row = await session.execute(select(UserXP).where(UserXP.user_id == user_id))
    user_xp = user_xp_row.scalar_one_or_none()
    if user_xp is None:
        return []

    new_badges = []

    async def _award_badge(key: str):
        if key in existing:
            return
        badge = _models.UserBadge(user_id=user_id, badge_key=key)
        session.add(badge)
        existing.add(key)
        new_badges.append(build_badge_response(key, earned_at=datetime.now(tz=timezone.utc)))

    # --- Source-based first-time badges ---
    if source == "mood_log":
        await _award_badge("first_mood")
    elif source == "journal_entry":
        await _award_badge("first_journal")
    elif source == "meditation_complete":
        await _award_badge("first_meditation")
    elif source == "therapist_session":
        await _award_badge("first_therapy")
    elif source == "goal_milestone":
        await _award_badge("goal_complete")

    # --- Streak badges ---
    if user_xp.current_streak_days >= 100:
        await _award_badge("streak_100")
    elif user_xp.current_streak_days >= 30:
        await _award_badge("streak_30")
    elif user_xp.current_streak_days >= 7:
        await _award_badge("streak_7")

    # --- Level badges ---
    if user_xp.level >= 10:
        await _award_badge("level_10")
    elif user_xp.level >= 5:
        await _award_badge("level_5")

    # --- Count-based badges ---
    if source == "meditation_complete":
        count_result = await session.execute(
            select(XPTransaction).where(
                XPTransaction.user_id == user_id,
                XPTransaction.source == "meditation_complete",
            )
        )
        if len(count_result.all()) >= 10:
            await _award_badge("meditation_10")

    if source == "journal_entry":
        count_result = await session.execute(
            select(XPTransaction).where(
                XPTransaction.user_id == user_id,
                XPTransaction.source == "journal_entry",
            )
        )
        if len(count_result.all()) >= 10:
            await _award_badge("journal_10")

    if source == "mood_log":
        count_result = await session.execute(
            select(XPTransaction).where(
                XPTransaction.user_id == user_id,
                XPTransaction.source == "mood_log",
            )
        )
        if len(count_result.all()) >= 30:
            await _award_badge("mood_30")

    # --- Daily challenge milestone ---
    if source == "daily_challenge":
        count_result = await session.execute(
            select(XPTransaction).where(
                XPTransaction.user_id == user_id,
                XPTransaction.source == "daily_challenge",
            )
        )
        if len(count_result.all()) >= 5:
            await _award_badge("five_challenges")

    await session.flush()
    return new_badges


# ---------------------------------------------------------------------------
# Primary public function
# ---------------------------------------------------------------------------

async def award_xp(
    session,
    user_id: str,
    source: str,
    description: str,
    base_amount: int | None = None,
) -> object:
    """Award XP for a user action and return an XPGainResponse.

    Steps:
    1. Get or create UserXP row.
    2. Determine base amount from XP_TABLE if not provided.
    3. Calculate streak multiplier and apply it.
    4. Insert XPTransaction.
    5. Update streak (advance or reset based on last_active_date).
    6. Recalculate level.
    7. Check for new badges.
    8. Return XPGainResponse.
    """
    _models = sys.modules["zugalife.gamification.models"]
    _schemas = sys.modules["zugalife.gamification.schemas"]
    UserXP = _models.UserXP
    XPTransaction = _models.XPTransaction

    today = date.today()

    user_xp = await _get_or_create_user_xp(session, user_id)

    # --- Determine base amount ---
    if base_amount is None:
        if source == "streak_bonus":
            base_amount = user_xp.current_streak_days * 5
        else:
            base_amount = XP_TABLE.get(source, 10)

    # --- Streak multiplier ---
    multiplier = compute_streak_multiplier(user_xp.current_streak_days)
    # streak_bonus is NOT multiplied by itself — that would compound incorrectly
    if source == "streak_bonus":
        xp_gained = base_amount
    else:
        xp_gained = max(1, round(base_amount * multiplier))

    # --- Record transaction ---
    tx = XPTransaction(
        user_id=user_id,
        amount=xp_gained,
        source=source,
        description=description[:200],
    )
    session.add(tx)

    # --- Update streak ---
    if user_xp.last_active_date is None:
        # First ever activity
        user_xp.current_streak_days = 1
    elif user_xp.last_active_date == today:
        # Already active today — streak unchanged
        pass
    elif (today - user_xp.last_active_date).days == 1:
        # Consecutive day — advance streak
        user_xp.current_streak_days += 1
    else:
        # Gap — reset streak
        user_xp.current_streak_days = 1

    user_xp.last_active_date = today
    if user_xp.current_streak_days > user_xp.longest_streak_days:
        user_xp.longest_streak_days = user_xp.current_streak_days

    # --- Update XP and level ---
    old_level = user_xp.level
    user_xp.total_xp += xp_gained
    new_level, _ = compute_level(user_xp.total_xp)
    user_xp.level = new_level
    level_up = new_level > old_level

    await session.flush()

    # --- Badge checks (after flush so counts include this transaction) ---
    new_badges = await _check_and_award_badges(session, user_id, source)

    return _schemas.XPGainResponse(
        xp_gained=xp_gained,
        new_total=user_xp.total_xp,
        level_up=level_up,
        new_level=new_level if level_up else None,
        new_badges=new_badges,
    )


async def ensure_daily_challenges(session, user_id: str, for_date: date | None = None) -> list:
    """Ensure today's challenges exist for the user, creating them if not.

    Returns the list of DailyChallenge ORM rows for today.
    """
    _models = sys.modules["zugalife.gamification.models"]
    DailyChallenge = _models.DailyChallenge

    if for_date is None:
        for_date = date.today()

    # Check if already generated
    result = await session.execute(
        select(DailyChallenge).where(
            DailyChallenge.user_id == user_id,
            DailyChallenge.challenge_date == for_date,
        )
    )
    rows = result.scalars().all()
    if rows:
        return rows

    # Generate deterministically
    picks = select_daily_challenges(user_id, for_date)
    new_rows = []
    for pick in picks:
        challenge = DailyChallenge(
            user_id=user_id,
            challenge_date=for_date,
            challenge_key=pick["key"],
            title=pick["title"],
            description=pick["desc"],
            xp_reward=pick["xp"],
        )
        session.add(challenge)
        new_rows.append(challenge)

    await session.flush()
    return new_rows


async def build_xp_status(session, user_id: str) -> object:
    """Read UserXP row and return an XPStatusResponse."""
    _models = sys.modules["zugalife.gamification.models"]
    _schemas = sys.modules["zugalife.gamification.schemas"]
    UserXP = _models.UserXP

    result = await session.execute(select(UserXP).where(UserXP.user_id == user_id))
    user_xp = result.scalar_one_or_none()

    if user_xp is None:
        # New user — return zeros
        return _schemas.XPStatusResponse(
            total_xp=0,
            level=1,
            level_name="Beginner",
            xp_for_next_level=100,
            xp_progress_in_level=0,
            current_streak_days=0,
            longest_streak_days=0,
            streak_multiplier=1.0,
        )

    level, level_name = compute_level(user_xp.total_xp)
    current_level_floor = xp_for_level(level)

    # Find the XP required to reach the NEXT level
    next_level_threshold = None
    for min_xp, lvl, _ in sorted(LEVELS, key=lambda x: x[0]):
        if lvl == level + 1:
            next_level_threshold = min_xp
            break
    if next_level_threshold is None:
        # Already at max level
        next_level_threshold = xp_for_level(10)

    xp_progress = user_xp.total_xp - current_level_floor
    xp_for_next = next_level_threshold - current_level_floor

    return _schemas.XPStatusResponse(
        total_xp=user_xp.total_xp,
        level=level,
        level_name=level_name,
        xp_for_next_level=xp_for_next,
        xp_progress_in_level=xp_progress,
        current_streak_days=user_xp.current_streak_days,
        longest_streak_days=user_xp.longest_streak_days,
        streak_multiplier=compute_streak_multiplier(user_xp.current_streak_days),
    )
