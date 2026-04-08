"""ZugaLife push notification system — subscription management, send logic, and scheduling.

Notification-only push (no caching/offline). Uses VAPID-signed web push via pywebpush.
Encouraging tone. Max 2 notifications per user per day. Respects quiet hours.

Scaled for many users:
  - Layer 1: Batch SQL queries (DB filters, not Python loops)
  - Layer 2: Async concurrent push delivery (semaphore-bounded asyncio.gather)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, Time, func, select
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PushSubscription(Base):
    """A user's push notification subscription (one per browser/device)."""

    __tablename__ = "life_push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh_key: Mapped[str] = mapped_column(String(200), nullable=False)
    auth_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationPreferences(Base):
    """Per-user notification settings — quiet hours, types, timing."""

    __tablename__ = "life_notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quiet_start: Mapped[time | None] = mapped_column(Time, nullable=True)  # e.g. 22:00
    quiet_end: Mapped[time | None] = mapped_column(Time, nullable=True)  # e.g. 08:00
    reminder_hour: Mapped[int] = mapped_column(Integer, default=9, nullable=False)  # 0-23
    streak_warnings: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    daily_nudges: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    milestone_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationLog(Base):
    """Audit log of sent notifications — for rate limiting and debugging."""

    __tablename__ = "life_notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# VAPID configuration
# ---------------------------------------------------------------------------


def _get_vapid_keys() -> tuple[str, str]:
    """Return (private_key, public_key) from environment."""
    private = os.environ.get("VAPID_PRIVATE_KEY", "")
    public = os.environ.get("VAPID_PUBLIC_KEY", "")
    if not private or not public:
        logger.warning("VAPID keys not configured — push notifications disabled")
    return private, public


def get_vapid_public_key() -> str:
    """Return the VAPID public key for frontend subscription."""
    _, public = _get_vapid_keys()
    return public


# ---------------------------------------------------------------------------
# Notification copy — encouraging tone
# ---------------------------------------------------------------------------

NOTIFICATION_TEMPLATES = {
    "streak_reminder": {
        "title": "Keep your streak alive! 🔥",
        "body": "You're on a {streak}-day streak — just one quick action to keep it going.",
        "url": "/life",
        "tag": "streak-reminder",
    },
    "daily_nudge": {
        "title": "Your day is waiting ✨",
        "body": "New challenges are ready — {xp_available} XP to earn today!",
        "url": "/life",
        "tag": "daily-nudge",
    },
    "level_close": {
        "title": "Almost there! 🎯",
        "body": "You're only {xp_remaining} XP from Level {next_level}. One session away!",
        "url": "/life",
        "tag": "level-close",
    },
    "freeze_warning": {
        "title": "No safety net 🧊",
        "body": "Your {streak}-day streak has no freeze protection. Earn one today!",
        "url": "/life",
        "tag": "freeze-warning",
    },
    "comeback": {
        "title": "We've been saving your spot 💫",
        "body": "Your wellness journey is waiting. Pick up where you left off!",
        "url": "/life",
        "tag": "comeback",
    },
    "milestone": {
        "title": "Milestone reached! 🎉",
        "body": "{message}",
        "url": "/life",
        "tag": "milestone",
    },
}

# Max notifications per user per day
MAX_DAILY_NOTIFICATIONS = 2


# ---------------------------------------------------------------------------
# Send logic (Layer 2: async concurrent delivery)
# ---------------------------------------------------------------------------

# Max concurrent webpush HTTP calls (prevents overwhelming push servers)
_PUSH_CONCURRENCY = 50


def _build_payload(notification_type: str, context: dict) -> str | None:
    """Build JSON payload for a notification type. Returns None if unknown type."""
    template = NOTIFICATION_TEMPLATES.get(notification_type)
    if not template:
        return None
    title = template["title"]
    body = template["body"].format(**context) if context else template["body"]
    return json.dumps({
        "title": title,
        "body": body,
        "url": template.get("url", "/life"),
        "tag": template.get("tag", "zugaapp"),
    })


def _is_in_quiet_hours(prefs) -> bool:
    """Check if current time falls within user's quiet hours."""
    if not prefs or not prefs.quiet_start or not prefs.quiet_end:
        return False
    now_time = datetime.now().time()
    if prefs.quiet_start > prefs.quiet_end:
        return now_time >= prefs.quiet_start or now_time <= prefs.quiet_end
    return prefs.quiet_start <= now_time <= prefs.quiet_end


def _type_allowed_by_prefs(prefs, notification_type: str) -> bool:
    """Check if a notification type is enabled in user preferences."""
    if not prefs:
        return True  # no prefs = all defaults on
    if not prefs.enabled:
        return False
    if notification_type == "streak_reminder" and not prefs.streak_warnings:
        return False
    if notification_type == "daily_nudge" and not prefs.daily_nudges:
        return False
    if notification_type in ("milestone", "level_close") and not prefs.milestone_alerts:
        return False
    return True


async def _deliver_push(sub, payload: str, vapid_key: str) -> tuple[bool, bool]:
    """Send a single webpush. Returns (success, should_deactivate).

    Runs the blocking webpush() call in a thread to avoid blocking the event loop.
    """
    try:
        from pywebpush import webpush

        await asyncio.to_thread(
            webpush,
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
            },
            data=payload,
            vapid_private_key=vapid_key,
            vapid_claims={"sub": "mailto:notifications@zugabot.ai"},
        )
        return True, False
    except Exception as exc:
        error_msg = str(exc)
        if "410" in error_msg or "404" in error_msg:
            return False, True  # subscription expired
        logger.warning("Push delivery failed: %s", error_msg[:100])
        return False, False


async def send_push_to_user(
    session, user_id: str, notification_type: str, context: dict | None = None
) -> bool:
    """Send a push notification to all active subscriptions for a user.

    Returns True if at least one notification was sent successfully.
    Respects rate limits and quiet hours.
    """
    context = context or {}
    today = date.today()

    # Check rate limit
    count_result = await session.execute(
        select(func.count()).where(
            NotificationLog.user_id == user_id,
            func.date(NotificationLog.sent_at) == today,
        )
    )
    if (count_result.scalar() or 0) >= MAX_DAILY_NOTIFICATIONS:
        return False

    # Check preferences + quiet hours
    prefs_result = await session.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()
    if not _type_allowed_by_prefs(prefs, notification_type):
        return False
    if _is_in_quiet_hours(prefs):
        return False

    # Build payload
    payload = _build_payload(notification_type, context)
    if not payload:
        return False

    # Get subscriptions
    subs_result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.is_active == True,
        )
    )
    subscriptions = subs_result.scalars().all()
    if not subscriptions:
        return False

    private_key, _ = _get_vapid_keys()
    if not private_key:
        return False

    # Deliver to all subscriptions concurrently
    results = await asyncio.gather(
        *[_deliver_push(sub, payload, private_key) for sub in subscriptions]
    )

    sent = False
    for (success, should_deactivate), sub in zip(results, subscriptions):
        if success:
            sent = True
        if should_deactivate:
            sub.is_active = False

    if sent:
        session.add(NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            title=NOTIFICATION_TEMPLATES[notification_type]["title"],
        ))
        await session.flush()
        logger.info("Push sent to %s (type=%s)", user_id[:8], notification_type)

    return sent


# ---------------------------------------------------------------------------
# Scheduler (Layer 1: batch queries + Layer 2: concurrent delivery)
# ---------------------------------------------------------------------------


async def check_and_send_notifications(session) -> dict:
    """Check all users and send applicable notifications.

    Layer 1: Uses batch SQL queries — the DB filters users, not Python.
    Layer 2: Collects all pending pushes, then delivers concurrently.

    Scales to 10,000+ users with ~5 queries + bounded concurrency.
    """
    _models = sys.modules.get("zugalife.gamification.models")
    _engine = sys.modules.get("zugalife.gamification.engine")
    if not _models:
        return {"error": "gamification models not loaded"}

    UserXP = _models.UserXP
    today = date.today()
    now_hour = datetime.now().hour
    summary = {"checked": 0, "sent": 0, "errors": 0}

    private_key, _ = _get_vapid_keys()
    if not private_key:
        return {"error": "VAPID keys not configured"}

    # ------------------------------------------------------------------
    # BULK PRE-LOAD: preferences, rate limits, subscriptions, sent log
    # (5 queries regardless of user count)
    # ------------------------------------------------------------------

    # All preferences keyed by user_id
    prefs_result = await session.execute(select(NotificationPreferences))
    prefs_by_user: dict[str, NotificationPreferences] = {
        p.user_id: p for p in prefs_result.scalars().all()
    }

    # Today's notification counts per user (for rate limiting)
    rate_result = await session.execute(
        select(NotificationLog.user_id, func.count().label("cnt"))
        .where(func.date(NotificationLog.sent_at) == today)
        .group_by(NotificationLog.user_id)
    )
    sent_today: dict[str, int] = {row.user_id: row.cnt for row in rate_result.all()}

    # Today's sent notification types per user (for dedup)
    dedup_result = await session.execute(
        select(NotificationLog.user_id, NotificationLog.notification_type)
        .where(func.date(NotificationLog.sent_at) == today)
    )
    sent_types: dict[str, set[str]] = {}
    for row in dedup_result.all():
        sent_types.setdefault(row.user_id, set()).add(row.notification_type)

    # Recent comeback notifications (last 3 days, for comeback dedup)
    comeback_cutoff = datetime.now(tz=timezone.utc) - timedelta(days=3)
    comeback_result = await session.execute(
        select(NotificationLog.user_id).where(
            NotificationLog.notification_type == "comeback",
            NotificationLog.sent_at >= comeback_cutoff,
        )
    )
    recent_comeback_users: set[str] = {row.user_id for row in comeback_result.all()}

    # All active subscriptions keyed by user_id
    subs_result = await session.execute(
        select(PushSubscription).where(PushSubscription.is_active == True)
    )
    subs_by_user: dict[str, list] = {}
    for sub in subs_result.scalars().all():
        subs_by_user.setdefault(sub.user_id, []).append(sub)

    # Users with active subscriptions = the only users we care about
    subscribable_user_ids = set(subs_by_user.keys())
    if not subscribable_user_ids:
        return {"checked": 0, "sent": 0, "errors": 0, "note": "no subscribers"}

    # ------------------------------------------------------------------
    # BATCH QUERIES: find qualifying users per notification type
    # Each query returns only users who match the criteria.
    # ------------------------------------------------------------------

    # Collect pending pushes: list of (user_id, notification_type, context)
    pending: list[tuple[str, str, dict]] = []

    # 1. Streak reminders (evening 18-21, not active today, streak >= 3)
    if 18 <= now_hour <= 21:
        result = await session.execute(
            select(UserXP).where(
                UserXP.user_id.in_(subscribable_user_ids),
                UserXP.last_active_date != today,
                UserXP.current_streak_days >= 3,
            )
        )
        for ux in result.scalars().all():
            pending.append((ux.user_id, "streak_reminder", {"streak": ux.current_streak_days}))

    # 2. Daily nudges (at user's preferred hour, not active today)
    # Default reminder_hour is 9 — fetch users matching current hour
    result = await session.execute(
        select(UserXP).where(
            UserXP.user_id.in_(subscribable_user_ids),
            UserXP.last_active_date != today,
        )
    )
    for ux in result.scalars().all():
        prefs = prefs_by_user.get(ux.user_id)
        reminder_hour = prefs.reminder_hour if prefs else 9
        if now_hour == reminder_hour:
            pending.append((ux.user_id, "daily_nudge", {"xp_available": "75+"}))

    # 3. Level close (active today, within 20% of next level)
    if _engine:
        result = await session.execute(
            select(UserXP).where(
                UserXP.user_id.in_(subscribable_user_ids),
                UserXP.last_active_date == today,
            )
        )
        for ux in result.scalars().all():
            level, _ = _engine.compute_level(ux.total_xp)
            current_floor = _engine.xp_for_level(level)
            next_floor = _engine.xp_for_level(level + 1)
            xp_needed = next_floor - ux.total_xp
            level_size = next_floor - current_floor
            if level_size > 0 and 0 < xp_needed <= level_size * 0.2:
                pending.append((ux.user_id, "level_close", {
                    "xp_remaining": xp_needed, "next_level": level + 1,
                }))

    # 4. Freeze warning (noon-3pm, streak >= 7, no freezes)
    if 12 <= now_hour <= 15:
        result = await session.execute(
            select(UserXP).where(
                UserXP.user_id.in_(subscribable_user_ids),
                UserXP.current_streak_days >= 7,
                UserXP.streak_freezes == 0,
            )
        )
        for ux in result.scalars().all():
            pending.append((ux.user_id, "freeze_warning", {"streak": ux.current_streak_days}))

    # 5. Comeback (3+ days inactive, at 10am)
    if now_hour == 10:
        cutoff_date = today - timedelta(days=3)
        result = await session.execute(
            select(UserXP).where(
                UserXP.user_id.in_(subscribable_user_ids),
                UserXP.last_active_date != None,
                UserXP.last_active_date <= cutoff_date,
            )
        )
        for ux in result.scalars().all():
            pending.append((ux.user_id, "comeback", {}))

    summary["checked"] = len(subscribable_user_ids)

    # ------------------------------------------------------------------
    # FILTER: apply rate limits, preferences, quiet hours, dedup
    # (pure Python, no DB queries — all data pre-loaded)
    # ------------------------------------------------------------------

    # Pick best notification per user (first match wins, no stacking)
    user_chosen: dict[str, tuple[str, dict]] = {}  # user_id → (type, context)
    for user_id, notif_type, context in pending:
        if user_id in user_chosen:
            continue  # already have a notification for this user

        # Rate limit check
        if sent_today.get(user_id, 0) >= MAX_DAILY_NOTIFICATIONS:
            continue

        # Dedup check (don't re-send same type today)
        if notif_type in sent_types.get(user_id, set()):
            continue

        # Comeback dedup (don't re-send within 3 days)
        if notif_type == "comeback" and user_id in recent_comeback_users:
            continue

        # Preferences + quiet hours
        prefs = prefs_by_user.get(user_id)
        if not _type_allowed_by_prefs(prefs, notif_type):
            continue
        if _is_in_quiet_hours(prefs):
            continue

        user_chosen[user_id] = (notif_type, context)

    if not user_chosen:
        return summary

    # ------------------------------------------------------------------
    # DELIVER: send all pushes concurrently (Layer 2)
    # ------------------------------------------------------------------

    semaphore = asyncio.Semaphore(_PUSH_CONCURRENCY)

    async def _send_one(user_id: str, notif_type: str, context: dict):
        payload = _build_payload(notif_type, context)
        if not payload:
            return False

        subs = subs_by_user.get(user_id, [])
        if not subs:
            return False

        async with semaphore:
            results = await asyncio.gather(
                *[_deliver_push(sub, payload, private_key) for sub in subs]
            )

        sent = False
        for (success, should_deactivate), sub in zip(results, subs):
            if success:
                sent = True
            if should_deactivate:
                sub.is_active = False

        if sent:
            session.add(NotificationLog(
                user_id=user_id,
                notification_type=notif_type,
                title=NOTIFICATION_TEMPLATES[notif_type]["title"],
            ))

        return sent

    # Fire all sends concurrently
    send_results = await asyncio.gather(*[
        _send_one(uid, ntype, ctx) for uid, (ntype, ctx) in user_chosen.items()
    ], return_exceptions=True)

    for result in send_results:
        if isinstance(result, Exception):
            summary["errors"] += 1
            logger.warning("Notification send error: %s", result)
        elif result:
            summary["sent"] += 1

    # Commit all logs + deactivations in one batch
    await session.flush()

    logger.info(
        "Notification check complete: %d subscribers, %d sent, %d errors",
        summary["checked"], summary["sent"], summary["errors"],
    )
    return summary
