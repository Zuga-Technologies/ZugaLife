"""ZugaLife push notification system — subscription management, send logic, and scheduling.

Notification-only push (no caching/offline). Uses VAPID-signed web push via pywebpush.
Encouraging tone. Max 2 notifications per user per day. Respects quiet hours.
"""

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
# Send logic
# ---------------------------------------------------------------------------


async def send_push_to_user(
    session, user_id: str, notification_type: str, context: dict | None = None
) -> bool:
    """Send a push notification to all active subscriptions for a user.

    Returns True if at least one notification was sent successfully.
    Respects rate limits and quiet hours.
    """
    context = context or {}

    # Check rate limit
    today = date.today()
    count_result = await session.execute(
        select(func.count()).where(
            NotificationLog.user_id == user_id,
            func.date(NotificationLog.sent_at) == today,
        )
    )
    sent_today = count_result.scalar() or 0
    if sent_today >= MAX_DAILY_NOTIFICATIONS:
        logger.debug("Rate limit reached for %s (%d/%d)", user_id[:8], sent_today, MAX_DAILY_NOTIFICATIONS)
        return False

    # Check preferences
    prefs_result = await session.execute(
        select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
    )
    prefs = prefs_result.scalar_one_or_none()

    if prefs and not prefs.enabled:
        return False

    # Check quiet hours
    if prefs and prefs.quiet_start and prefs.quiet_end:
        now_time = datetime.now().time()
        if prefs.quiet_start > prefs.quiet_end:
            # Overnight quiet hours (e.g., 22:00 to 08:00)
            if now_time >= prefs.quiet_start or now_time <= prefs.quiet_end:
                logger.debug("Quiet hours active for %s", user_id[:8])
                return False
        else:
            if prefs.quiet_start <= now_time <= prefs.quiet_end:
                logger.debug("Quiet hours active for %s", user_id[:8])
                return False

    # Check per-type preferences
    if prefs:
        if notification_type == "streak_reminder" and not prefs.streak_warnings:
            return False
        if notification_type == "daily_nudge" and not prefs.daily_nudges:
            return False
        if notification_type in ("milestone", "level_close") and not prefs.milestone_alerts:
            return False

    # Build notification payload
    template = NOTIFICATION_TEMPLATES.get(notification_type)
    if not template:
        logger.warning("Unknown notification type: %s", notification_type)
        return False

    title = template["title"]
    body = template["body"].format(**context) if context else template["body"]
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": template.get("url", "/life"),
        "tag": template.get("tag", "zugaapp"),
    })

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

    sent = False
    for sub in subscriptions:
        try:
            from pywebpush import webpush, WebPushException

            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh_key,
                        "auth": sub.auth_key,
                    },
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": "mailto:notifications@zugabot.ai"},
            )
            sent = True
            logger.info("Push sent to %s (type=%s)", user_id[:8], notification_type)
        except Exception as exc:
            error_msg = str(exc)
            # 410 Gone = subscription expired, deactivate it
            if "410" in error_msg or "404" in error_msg:
                sub.is_active = False
                logger.info("Deactivated expired subscription for %s", user_id[:8])
            else:
                logger.warning("Push failed for %s: %s", user_id[:8], error_msg)

    # Log the notification
    if sent:
        log_entry = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
        )
        session.add(log_entry)
        await session.flush()

    return sent


# ---------------------------------------------------------------------------
# Scheduler — checks all users and sends applicable notifications
# ---------------------------------------------------------------------------


async def check_and_send_notifications(session) -> dict:
    """Check all users and send applicable notifications.

    Called periodically (e.g., every hour by daemon or cron).
    Returns summary dict with counts.
    """
    _models = sys.modules.get("zugalife.gamification.models")
    if not _models:
        return {"error": "gamification models not loaded"}

    UserXP = _models.UserXP
    today = date.today()
    now_hour = datetime.now().hour
    summary = {"checked": 0, "sent": 0, "skipped": 0}

    # Get all users with gamification data
    result = await session.execute(select(UserXP))
    users = result.scalars().all()

    for user_xp in users:
        summary["checked"] += 1
        user_id = user_xp.user_id

        # --- Streak reminder (evening: 18:00-21:00, if no activity today) ---
        if 18 <= now_hour <= 21:
            if (
                user_xp.last_active_date != today
                and user_xp.current_streak_days >= 3
            ):
                sent = await send_push_to_user(
                    session, user_id, "streak_reminder",
                    {"streak": user_xp.current_streak_days},
                )
                if sent:
                    summary["sent"] += 1
                    continue  # Don't stack notifications

        # --- Daily nudge (morning: user's preferred hour, default 9) ---
        prefs_result = await session.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        prefs = prefs_result.scalar_one_or_none()
        reminder_hour = prefs.reminder_hour if prefs else 9

        if now_hour == reminder_hour and user_xp.last_active_date != today:
            sent = await send_push_to_user(
                session, user_id, "daily_nudge",
                {"xp_available": "75+"},
            )
            if sent:
                summary["sent"] += 1
                continue

        # --- Level close (anytime, if within 20% of next level) ---
        _engine = sys.modules.get("zugalife.gamification.engine")
        if _engine and user_xp.last_active_date == today:
            level, _ = _engine.compute_level(user_xp.total_xp)
            current_floor = _engine.xp_for_level(level)
            next_floor = _engine.xp_for_level(level + 1)
            xp_needed = next_floor - user_xp.total_xp
            level_size = next_floor - current_floor

            if level_size > 0 and xp_needed <= level_size * 0.2 and xp_needed > 0:
                # Only send once per day for level-close
                already_sent = await session.execute(
                    select(func.count()).where(
                        NotificationLog.user_id == user_id,
                        NotificationLog.notification_type == "level_close",
                        func.date(NotificationLog.sent_at) == today,
                    )
                )
                if (already_sent.scalar() or 0) == 0:
                    sent = await send_push_to_user(
                        session, user_id, "level_close",
                        {"xp_remaining": xp_needed, "next_level": level + 1},
                    )
                    if sent:
                        summary["sent"] += 1
                        continue

        # --- Freeze warning (if streak >= 7, no freezes, haven't sent today) ---
        if (
            user_xp.current_streak_days >= 7
            and user_xp.streak_freezes == 0
            and 12 <= now_hour <= 15
        ):
            already_sent = await session.execute(
                select(func.count()).where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.notification_type == "freeze_warning",
                    func.date(NotificationLog.sent_at) == today,
                )
            )
            if (already_sent.scalar() or 0) == 0:
                sent = await send_push_to_user(
                    session, user_id, "freeze_warning",
                    {"streak": user_xp.current_streak_days},
                )
                if sent:
                    summary["sent"] += 1
                    continue

        # --- Comeback (3+ days inactive) ---
        if user_xp.last_active_date and (today - user_xp.last_active_date).days >= 3:
            if now_hour == 10:  # Send comebacks at 10am
                already_sent = await session.execute(
                    select(func.count()).where(
                        NotificationLog.user_id == user_id,
                        NotificationLog.notification_type == "comeback",
                        NotificationLog.sent_at >= datetime.now(tz=timezone.utc) - timedelta(days=3),
                    )
                )
                if (already_sent.scalar() or 0) == 0:
                    sent = await send_push_to_user(
                        session, user_id, "comeback", {},
                    )
                    if sent:
                        summary["sent"] += 1
                        continue

        summary["skipped"] += 1

    return summary
