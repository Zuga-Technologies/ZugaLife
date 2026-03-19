"""Shared helper to get a user's timezone-aware 'today'.

Used by mood routes, habit routes, and dashboard to calculate
streaks based on the user's local midnight — not UTC.
"""

import sys
import zoneinfo
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select


async def get_user_today(session, user_id: str) -> date:
    """Return today's date in the user's configured timezone.

    Falls back to America/New_York if no settings row exists.
    This is the critical fix: streaks should reset at the USER's
    midnight, not UTC midnight.
    """
    LifeUserSettings = sys.modules["zugalife.settings_models"].LifeUserSettings

    result = await session.execute(
        select(LifeUserSettings.timezone)
        .where(LifeUserSettings.user_id == user_id)
    )
    tz_name = result.scalar_one_or_none() or "America/New_York"

    try:
        user_tz = ZoneInfo(tz_name)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        user_tz = ZoneInfo("America/New_York")

    return datetime.now(user_tz).date()
