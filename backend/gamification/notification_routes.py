"""ZugaLife notification endpoints — subscription, preferences, VAPID key, and trigger."""

import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling module loaded by plugin.py
_notif = sys.modules["zugalife.gamification.notifications"]

PushSubscription = _notif.PushSubscription
NotificationPreferences = _notif.NotificationPreferences

router = APIRouter(prefix="/api/life/notifications", tags=["life-notifications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PreferencesRequest(BaseModel):
    enabled: bool = True
    quiet_start: str | None = None  # "22:00" or null
    quiet_end: str | None = None  # "08:00" or null
    reminder_hour: int = 9  # 0-23
    streak_warnings: bool = True
    daily_nudges: bool = True
    milestone_alerts: bool = True


class PreferencesResponse(BaseModel):
    enabled: bool
    quiet_start: str | None
    quiet_end: str | None
    reminder_hour: int
    streak_warnings: bool
    daily_nudges: bool
    milestone_alerts: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for frontend push subscription."""
    key = _notif.get_vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"vapid_public_key": key}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Register a push subscription for the authenticated user."""
    async with get_session() as session:
        # Check if subscription already exists (same endpoint)
        existing = await session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.endpoint == body.endpoint,
            )
        )
        sub = existing.scalar_one_or_none()

        if sub:
            # Update keys (browser may refresh them)
            sub.p256dh_key = body.p256dh
            sub.auth_key = body.auth
            sub.is_active = True
        else:
            sub = PushSubscription(
                user_id=user.id,
                endpoint=body.endpoint,
                p256dh_key=body.p256dh,
                auth_key=body.auth,
            )
            session.add(sub)

        # Ensure preferences exist
        prefs_result = await session.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user.id
            )
        )
        if not prefs_result.scalar_one_or_none():
            session.add(NotificationPreferences(user_id=user.id))

        await session.flush()

    return {"status": "subscribed"}


@router.delete("/unsubscribe")
async def unsubscribe(
    user: CurrentUser = Depends(get_current_user),
):
    """Deactivate all push subscriptions for the authenticated user."""
    async with get_session() as session:
        result = await session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user.id,
                PushSubscription.is_active == True,
            )
        )
        subs = result.scalars().all()
        for sub in subs:
            sub.is_active = False
        await session.flush()

    return {"status": "unsubscribed", "deactivated": len(subs)}


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user: CurrentUser = Depends(get_current_user),
):
    """Get notification preferences for the authenticated user."""
    async with get_session() as session:
        result = await session.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user.id
            )
        )
        prefs = result.scalar_one_or_none()

    if not prefs:
        return PreferencesResponse(
            enabled=True,
            quiet_start=None,
            quiet_end=None,
            reminder_hour=9,
            streak_warnings=True,
            daily_nudges=True,
            milestone_alerts=True,
        )

    return PreferencesResponse(
        enabled=prefs.enabled,
        quiet_start=prefs.quiet_start.strftime("%H:%M") if prefs.quiet_start else None,
        quiet_end=prefs.quiet_end.strftime("%H:%M") if prefs.quiet_end else None,
        reminder_hour=prefs.reminder_hour,
        streak_warnings=prefs.streak_warnings,
        daily_nudges=prefs.daily_nudges,
        milestone_alerts=prefs.milestone_alerts,
    )


@router.put("/preferences", response_model=PreferencesResponse)
async def update_preferences(
    body: PreferencesRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update notification preferences for the authenticated user."""
    from datetime import time as dt_time

    async with get_session() as session:
        result = await session.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user.id
            )
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            prefs = NotificationPreferences(user_id=user.id)
            session.add(prefs)

        prefs.enabled = body.enabled
        prefs.quiet_start = (
            dt_time.fromisoformat(body.quiet_start) if body.quiet_start else None
        )
        prefs.quiet_end = (
            dt_time.fromisoformat(body.quiet_end) if body.quiet_end else None
        )
        prefs.reminder_hour = max(0, min(23, body.reminder_hour))
        prefs.streak_warnings = body.streak_warnings
        prefs.daily_nudges = body.daily_nudges
        prefs.milestone_alerts = body.milestone_alerts

        await session.flush()

    return PreferencesResponse(
        enabled=prefs.enabled,
        quiet_start=body.quiet_start,
        quiet_end=body.quiet_end,
        reminder_hour=prefs.reminder_hour,
        streak_warnings=prefs.streak_warnings,
        daily_nudges=prefs.daily_nudges,
        milestone_alerts=prefs.milestone_alerts,
    )


@router.post("/trigger-check")
async def trigger_notification_check(
    user: CurrentUser = Depends(get_current_user),
):
    """Manually trigger the notification scheduler check.

    Intended for daemon/cron or admin testing.
    """
    async with get_session() as session:
        summary = await _notif.check_and_send_notifications(session)
    return summary
