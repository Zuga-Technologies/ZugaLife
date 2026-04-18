"""ZugaLife gamification pre-warm scheduler.

Phase 1 of the challenges/quests read-path decoupling. The first user
request of the day would otherwise trigger a synchronous LLM call inside
`ensure_daily_challenges` / `ensure_weekly_quests`, adding seconds to the
dashboard's first paint. This module moves that generation off the
request lifecycle onto a background task that runs once per UTC day.

The read path in routes.py still calls the same `ensure_*` helpers, so
users that signed up after the last sweep, or requests that hit during a
deploy restart, fall back to inline generation. Phase 1 is additive.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.database.session import get_session

logger = logging.getLogger(__name__)


def _engine():
    return sys.modules["zugalife.gamification.engine"]


def _user_xp_model():
    return sys.modules["zugalife.gamification.models"].UserXP


async def _active_user_ids() -> list[str]:
    """Users who have touched gamification at least once.

    UserXP rather than UserSettings: a row only exists after award_xp
    fired, so this filter skips SuperTokens users who never opened
    ZugaLife and avoids LLM spend on them.
    """
    UserXP = _user_xp_model()
    async with get_session() as session:
        result = await session.execute(select(UserXP.user_id))
        return [row[0] for row in result.all()]


async def _prewarm_one(user_id: str, semaphore: asyncio.Semaphore) -> bool:
    """Pre-generate today's challenges + this week's quests for one user.

    A fresh session per user — an LLM call holding a shared transaction
    open across the whole sweep would serialise everyone behind it.
    """
    engine = _engine()
    async with semaphore:
        try:
            async with get_session() as session:
                await engine.ensure_daily_challenges(session, user_id)
                await engine.ensure_weekly_quests(session, user_id)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning("prewarm failed for %s: %s", user_id[:8], exc)
            return False


async def prewarm_all_active_users(max_concurrency: int = 3) -> dict:
    """Run one prewarm sweep. Idempotent — safe to call repeatedly."""
    start = datetime.now(timezone.utc)
    user_ids = await _active_user_ids()
    if not user_ids:
        logger.info("prewarm: no active users")
        return {"users": 0, "ok": 0, "failed": 0, "duration_s": 0.0}

    semaphore = asyncio.Semaphore(max_concurrency)
    results = await asyncio.gather(
        *[_prewarm_one(uid, semaphore) for uid in user_ids],
    )
    ok = sum(1 for r in results if r)
    duration = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "prewarm complete: users=%d ok=%d failed=%d duration=%.2fs",
        len(user_ids), ok, len(user_ids) - ok, duration,
    )
    return {
        "users": len(user_ids),
        "ok": ok,
        "failed": len(user_ids) - ok,
        "duration_s": round(duration, 2),
    }


def _seconds_until_next_utc_hour(hour: int) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def scheduler_loop(target_hour_utc: int = 5, max_concurrency: int = 3) -> None:
    """Sleep until the next target UTC hour, run a sweep, repeat forever.

    Exceptions inside a sweep are logged but never break the loop, so
    one bad iteration (LLM outage, DB hiccup) does not disarm the
    scheduler — tomorrow's run still fires.
    """
    logger.info("challenge prewarm scheduler armed (hour=%02d:00 UTC)", target_hour_utc)
    while True:
        delay = _seconds_until_next_utc_hour(target_hour_utc)
        logger.info("next prewarm sweep in %.0f min", delay / 60)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("prewarm scheduler cancelled")
            raise
        try:
            await prewarm_all_active_users(max_concurrency=max_concurrency)
        except Exception as exc:
            logger.exception("prewarm sweep crashed: %s", exc)


def start_scheduler_task() -> asyncio.Task | None:
    """Spawn scheduler_loop as a background task. Returns the Task handle
    (or None if explicitly disabled) so the plugin can cancel it on
    shutdown.

    Env knobs:
      ZUGALIFE_PREWARM_ENABLED      — "0" to disable (default on)
      ZUGALIFE_PREWARM_UTC_HOUR     — 0-23, default 5 (past midnight in all US tz)
      ZUGALIFE_PREWARM_CONCURRENCY  — semaphore size, default 3
    """
    if os.getenv("ZUGALIFE_PREWARM_ENABLED", "1") == "0":
        logger.info("challenge prewarm scheduler disabled by env")
        return None
    hour = int(os.getenv("ZUGALIFE_PREWARM_UTC_HOUR", "5"))
    concurrency = int(os.getenv("ZUGALIFE_PREWARM_CONCURRENCY", "3"))
    return asyncio.create_task(
        scheduler_loop(target_hour_utc=hour, max_concurrency=concurrency),
        name="zugalife-challenge-prewarm",
    )
