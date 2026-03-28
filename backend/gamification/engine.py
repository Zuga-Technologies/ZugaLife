"""ZugaLife gamification engine — XP awards, level calculation, badge checks, prestige, and daily challenges.

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
import logging
import sys
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static lookup tables
# ---------------------------------------------------------------------------

# XP awarded per source action (base, before streak/prestige multipliers)
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

# ---------------------------------------------------------------------------
# Infinite leveling system — 25 levels per prestige cycle
# ---------------------------------------------------------------------------

PRESTIGE_LEVEL = 25  # Level at which prestige becomes available
PRESTIGE_XP_BONUS = 0.05  # +5% XP per prestige tier

# Level names — levels 1-25 have unique names, beyond that cycles back
LEVEL_NAMES: dict[int, str] = {
    1: "Beginner",
    2: "Explorer",
    3: "Seeker",
    4: "Practitioner",
    5: "Achiever",
    6: "Dedicated",
    7: "Mindful",
    8: "Resilient",
    9: "Master",
    10: "Enlightened",
    11: "Awakened",
    12: "Focused",
    13: "Disciplined",
    14: "Empowered",
    15: "Transcendent",
    16: "Harmonious",
    17: "Luminous",
    18: "Sovereign",
    19: "Ascendant",
    20: "Legendary",
    21: "Mythic",
    22: "Eternal",
    23: "Celestial",
    24: "Divine",
    25: "Transcended",
}

# XP cost to advance FROM level N to N+1 (dampened growth, caps at 3000)
# Levels 1-10 preserve original curve, 11+ grow linearly then flatten
_LEVEL_COSTS: dict[int, int] = {
    1: 100, 2: 200, 3: 300, 4: 400, 5: 500,
    6: 700, 7: 800, 8: 1000, 9: 1500,
}  # levels 10+ use formula


def _level_cost(level: int) -> int:
    """XP required to go from `level` to `level + 1`."""
    if level in _LEVEL_COSTS:
        return _LEVEL_COSTS[level]
    # Dampened linear growth: 1200 base + 120 per level above 10, capped at 3000
    return min(3000, 1200 + (level - 10) * 120)


def _cumulative_xp(level: int) -> int:
    """Total XP needed to reach `level` (from level 1)."""
    total = 0
    for lvl in range(1, level):
        total += _level_cost(lvl)
    return total


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
    "level_10":         {"title": "Enlightened",        "description": "Reached level 10",                        "emoji": "👑"},
    "level_25":         {"title": "Transcended",        "description": "Reached level 25",                        "emoji": "🌟"},
    "meditation_10":    {"title": "Zen Master",         "description": "Completed 10 meditation sessions",        "emoji": "🪷"},
    "journal_10":       {"title": "Storyteller",        "description": "Wrote 10 journal entries",                "emoji": "📚"},
    "mood_30":          {"title": "Self Aware",         "description": "Logged 30 moods",                         "emoji": "🔮"},
    "goal_complete":    {"title": "Goal Getter",        "description": "Completed your first goal",               "emoji": "🎯"},
    "five_challenges":  {"title": "Challenge Accepted", "description": "Completed 5 daily challenges",            "emoji": "🏆"},
}

# Prestige badge emojis — cycle through these for prestige tiers
_PRESTIGE_EMOJIS = ["🌟", "💫", "✨", "🔱", "👑", "💎", "🌠", "🏅"]


def get_prestige_badge(prestige_tier: int) -> dict:
    """Generate badge metadata for a prestige tier (1-indexed)."""
    emoji = _PRESTIGE_EMOJIS[(prestige_tier - 1) % len(_PRESTIGE_EMOJIS)]
    if prestige_tier == 1:
        title = "First Ascension"
    elif prestige_tier == 2:
        title = "Second Ascension"
    elif prestige_tier == 3:
        title = "Third Ascension"
    else:
        title = f"Ascension {prestige_tier}"
    return {
        "title": title,
        "description": f"Prestiged {prestige_tier} time{'s' if prestige_tier > 1 else ''}",
        "emoji": emoji,
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
    """Return (level_number, level_name) for a given total XP.

    Works for infinite levels — walks up the cost curve until XP is exhausted.
    """
    level = 1
    xp_remaining = total_xp
    while True:
        cost = _level_cost(level)
        if xp_remaining < cost:
            break
        xp_remaining -= cost
        level += 1
    name = LEVEL_NAMES.get(level, f"Level {level}")
    return level, name


def xp_for_level(level: int) -> int:
    """Return the total cumulative XP to reach a given level."""
    return _cumulative_xp(level)


def compute_streak_multiplier(streak_days: int) -> float:
    if streak_days >= 30:
        return 2.0
    if streak_days >= 7:
        return 1.5
    return 1.0


def compute_prestige_multiplier(prestige_level: int) -> float:
    """Return the permanent XP multiplier granted by prestige tiers."""
    return 1.0 + prestige_level * PRESTIGE_XP_BONUS


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
    # Check for prestige badges (prestige_1, prestige_2, ...)
    if badge_key.startswith("prestige_"):
        tier = int(badge_key.split("_")[1])
        meta = get_prestige_badge(tier)
    else:
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
    if user_xp.level >= 25:
        await _award_badge("level_25")
    if user_xp.level >= 10:
        await _award_badge("level_10")
    if user_xp.level >= 5:
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
    streak_mult = compute_streak_multiplier(user_xp.current_streak_days)
    prestige_mult = compute_prestige_multiplier(user_xp.prestige_level)
    # streak_bonus is NOT multiplied by streak (that would compound incorrectly)
    # but prestige multiplier applies to everything
    if source == "streak_bonus":
        xp_gained = max(1, round(base_amount * prestige_mult))
    else:
        xp_gained = max(1, round(base_amount * streak_mult * prestige_mult))

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

    # --- Auto-complete matching challenges (skip if source is daily_challenge to avoid loops) ---
    challenge_bonus = 0
    if source != "daily_challenge":
        challenge_bonus = await _check_challenge_completion(session, user_id, source)
        if challenge_bonus > 0:
            user_xp.total_xp += challenge_bonus
            xp_gained += challenge_bonus
            new_level_after, _ = compute_level(user_xp.total_xp)
            if new_level_after > new_level:
                level_up = True
                new_level = new_level_after
            user_xp.level = new_level_after
            await session.flush()

    return _schemas.XPGainResponse(
        xp_gained=xp_gained,
        new_total=user_xp.total_xp,
        level_up=level_up,
        new_level=new_level if level_up else None,
        new_badges=new_badges,
    )


async def _check_challenge_completion(session, user_id: str, source: str) -> int:
    """Check if any uncompleted daily challenge or weekly quest matches this action source.

    Auto-completes matching challenges and returns total bonus XP awarded.
    Records XP transactions for each completed challenge.
    """
    _models = sys.modules["zugalife.gamification.models"]
    DailyChallenge = _models.DailyChallenge
    WeeklyQuest = _models.WeeklyQuest
    XPTransaction = _models.XPTransaction

    today = date.today()
    total_bonus = 0

    # Check daily challenges
    result = await session.execute(
        select(DailyChallenge).where(
            DailyChallenge.user_id == user_id,
            DailyChallenge.challenge_date == today,
            DailyChallenge.is_completed == False,
            DailyChallenge.completion_source == source,
        )
    )
    daily_matches = result.scalars().all()

    for challenge in daily_matches:
        challenge.is_completed = True
        challenge.completed_at = datetime.now(tz=timezone.utc)
        total_bonus += challenge.xp_reward
        session.add(XPTransaction(
            user_id=user_id,
            amount=challenge.xp_reward,
            source="daily_challenge",
            description=f"Challenge: {challenge.title}",
        ))

    # Check weekly quests
    week_start = today - __import__("datetime").timedelta(days=today.weekday())
    result = await session.execute(
        select(WeeklyQuest).where(
            WeeklyQuest.user_id == user_id,
            WeeklyQuest.week_start == week_start,
            WeeklyQuest.is_completed == False,
            WeeklyQuest.completion_source == source,
        )
    )
    weekly_matches = result.scalars().all()

    for quest in weekly_matches:
        quest.is_completed = True
        quest.completed_at = datetime.now(tz=timezone.utc)
        total_bonus += quest.xp_reward
        session.add(XPTransaction(
            user_id=user_id,
            amount=quest.xp_reward,
            source="daily_challenge",
            description=f"Weekly quest: {quest.title}",
        ))

    if total_bonus > 0:
        await session.flush()

    return total_bonus


async def ensure_daily_challenges(
    session, user_id: str, for_date: date | None = None, user_email: str | None = None,
) -> list:
    """Ensure today's challenges exist for the user, creating them if not.

    Tries AI generation first. Falls back to static pool on failure.
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
        # If rows have empty titles (from failed AI generation), delete and regenerate
        if all(r.title for r in rows):
            logger.info("Returning %d existing challenges for %s", len(rows), user_id[:8])
            return rows
        logger.warning("Deleting %d malformed challenge rows for %s", len(rows), user_id[:8])
        for r in rows:
            await session.delete(r)
        await session.flush()

    # Try AI generation first
    ai_picks = None
    try:
        _ai = sys.modules.get("zugalife.gamification.ai_challenges")
        if _ai:
            ai_picks = await _ai.generate_challenges(
                session, user_id, challenge_type="daily", user_email=user_email,
            )
    except Exception as exc:
        logger.warning("AI challenge generation error: %s", exc)

    if ai_picks:
        picks = ai_picks
        is_ai = True
        logger.info("AI generated %d daily challenges for %s", len(ai_picks), user_id[:8])
    else:
        # Fallback to static deterministic pool
        picks = select_daily_challenges(user_id, for_date)
        is_ai = False
        logger.info("Static fallback: %d daily challenges for %s", len(picks), user_id[:8])

    # Get source mapping for static challenges
    _ai_mod = sys.modules.get("zugalife.gamification.ai_challenges")
    static_sources = getattr(_ai_mod, "STATIC_CHALLENGE_SOURCES", {}) if _ai_mod else {}

    new_rows = []
    for pick in picks[:3]:  # Always cap at 3
        source = pick.get("source") or static_sources.get(pick["key"])
        challenge = DailyChallenge(
            user_id=user_id,
            challenge_date=for_date,
            challenge_key=pick["key"],
            title=pick["title"],
            description=pick["desc"],
            xp_reward=pick["xp"],
            is_ai_generated=is_ai,
            completion_source=source,
        )
        session.add(challenge)
        new_rows.append(challenge)

    await session.flush()
    return new_rows


async def ensure_weekly_quests(
    session, user_id: str, user_email: str | None = None,
) -> list:
    """Ensure this week's quests exist for the user, creating them if not.

    Weekly quests are always AI-generated. Falls back to empty list if AI fails
    (weekly quests are a bonus, not required).
    """
    _models = sys.modules["zugalife.gamification.models"]
    WeeklyQuest = _models.WeeklyQuest

    today = date.today()
    # Week starts on Monday
    week_start = today - __import__("datetime").timedelta(days=today.weekday())

    # Check if already generated
    result = await session.execute(
        select(WeeklyQuest).where(
            WeeklyQuest.user_id == user_id,
            WeeklyQuest.week_start == week_start,
        )
    )
    rows = result.scalars().all()
    if rows:
        return rows

    # Generate via AI
    ai_quests = None
    try:
        _ai = sys.modules.get("zugalife.gamification.ai_challenges")
        if _ai:
            ai_quests = await _ai.generate_challenges(
                session, user_id, challenge_type="weekly", user_email=user_email,
            )
    except Exception:
        pass

    if not ai_quests:
        return []  # Weekly quests are optional — no static fallback

    new_rows = []
    for quest in ai_quests[:2]:  # Cap at 2
        row = WeeklyQuest(
            user_id=user_id,
            week_start=week_start,
            quest_key=quest["key"],
            title=quest["title"],
            description=quest["desc"],
            xp_reward=quest["xp"],
            completion_source=quest.get("source"),
        )
        session.add(row)
        new_rows.append(row)

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
        return _schemas.XPStatusResponse(
            total_xp=0,
            level=1,
            level_name="Beginner",
            xp_for_next_level=100,
            xp_progress_in_level=0,
            current_streak_days=0,
            longest_streak_days=0,
            streak_multiplier=1.0,
            prestige_level=0,
            prestige_multiplier=1.0,
            can_prestige=False,
        )

    level, level_name = compute_level(user_xp.total_xp)
    current_level_floor = xp_for_level(level)
    next_level_floor = xp_for_level(level + 1)

    xp_progress = user_xp.total_xp - current_level_floor
    xp_for_next = next_level_floor - current_level_floor

    can_prestige = level >= PRESTIGE_LEVEL

    return _schemas.XPStatusResponse(
        total_xp=user_xp.total_xp,
        level=level,
        level_name=level_name,
        xp_for_next_level=xp_for_next,
        xp_progress_in_level=xp_progress,
        current_streak_days=user_xp.current_streak_days,
        longest_streak_days=user_xp.longest_streak_days,
        streak_multiplier=compute_streak_multiplier(user_xp.current_streak_days),
        prestige_level=user_xp.prestige_level,
        prestige_multiplier=compute_prestige_multiplier(user_xp.prestige_level),
        can_prestige=can_prestige,
    )


async def perform_prestige(session, user_id: str) -> object:
    """Execute prestige: reset level/XP, increment prestige tier, award badge.

    Returns a PrestigeResponse. Raises ValueError if user can't prestige yet.
    """
    _models = sys.modules["zugalife.gamification.models"]
    _schemas = sys.modules["zugalife.gamification.schemas"]
    UserXP = _models.UserXP
    UserBadge = _models.UserBadge

    result = await session.execute(select(UserXP).where(UserXP.user_id == user_id))
    user_xp = result.scalar_one_or_none()

    if user_xp is None:
        raise ValueError("No gamification data found")

    level, _ = compute_level(user_xp.total_xp)
    if level < PRESTIGE_LEVEL:
        raise ValueError(f"Must reach level {PRESTIGE_LEVEL} to prestige (currently {level})")

    old_prestige = user_xp.prestige_level
    new_prestige = old_prestige + 1

    # Reset XP and level, keep streaks and badges
    user_xp.total_xp = 0
    user_xp.level = 1
    user_xp.prestige_level = new_prestige

    # Award prestige badge
    badge_key = f"prestige_{new_prestige}"
    badge = UserBadge(user_id=user_id, badge_key=badge_key)
    session.add(badge)

    await session.flush()

    badge_meta = get_prestige_badge(new_prestige)
    new_badge = _schemas.BadgeResponse(
        badge_key=badge_key,
        title=badge_meta["title"],
        description=badge_meta["description"],
        emoji=badge_meta["emoji"],
        earned_at=datetime.now(tz=timezone.utc),
    )

    return _schemas.PrestigeResponse(
        new_prestige_level=new_prestige,
        prestige_multiplier=compute_prestige_multiplier(new_prestige),
        badge=new_badge,
    )
