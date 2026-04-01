"""ZugaLife user settings endpoints.

GET  /api/life/settings  → return current settings (auto-create if missing)
PUT  /api/life/settings  → upsert settings (partial update)
"""

import sys

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

_models = sys.modules["zugalife.settings_models"]
_schemas = sys.modules["zugalife.settings_schemas"]

LifeUserSettings = _models.LifeUserSettings
LifeSettingsResponse = _schemas.LifeSettingsResponse
LifeSettingsUpdate = _schemas.LifeSettingsUpdate
VALID_THEMES = _schemas.VALID_THEMES
VALID_VOICES = _schemas.VALID_VOICES
VALID_AMBIENCES = _schemas.VALID_AMBIENCES

router = APIRouter(prefix="/api/life", tags=["life-settings"])


async def _get_or_create_settings(session, user_id: str) -> LifeUserSettings:
    """Return the user's settings row, creating one with defaults if missing."""
    result = await session.execute(
        select(LifeUserSettings).where(LifeUserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = LifeUserSettings(user_id=user_id)
        session.add(settings)
        await session.flush()
        await session.refresh(settings)
    return settings


@router.get("/settings", response_model=LifeSettingsResponse)
async def get_settings(
    user: CurrentUser = Depends(get_current_user),
):
    """Return current user settings. Auto-creates defaults on first call."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
    return LifeSettingsResponse.model_validate(settings)


@router.put("/settings", response_model=LifeSettingsResponse)
async def update_settings(
    body: LifeSettingsUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Update user settings. Only provided fields are changed."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)

        updates = body.model_dump(exclude_unset=True)

        # Validate enum-like fields
        if "theme" in updates and updates["theme"] not in VALID_THEMES:
            raise HTTPException(400, f"Invalid theme. Allowed: {sorted(VALID_THEMES)}")
        if "med_voice" in updates and updates["med_voice"] not in VALID_VOICES:
            raise HTTPException(400, f"Invalid voice. Allowed: {sorted(VALID_VOICES)}")
        if "med_ambience" in updates and updates["med_ambience"] not in VALID_AMBIENCES:
            raise HTTPException(400, f"Invalid ambience. Allowed: {sorted(VALID_AMBIENCES)}")

        # Validate timezone
        if "timezone" in updates:
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(updates["timezone"])
            except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                raise HTTPException(400, f"Invalid timezone: {updates['timezone']}")

        for field, value in updates.items():
            setattr(settings, field, value)

        await session.flush()
        await session.refresh(settings)

    return LifeSettingsResponse.model_validate(settings)


# ── Studio Onboarding ────────────────────────────────────────────


@router.get("/onboarding")
async def get_life_onboarding(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check if the user has completed ZugaLife studio onboarding."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
        return {"completed": bool(settings.onboarding_completed)}


@router.post("/onboarding/complete")
async def complete_life_onboarding(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Mark ZugaLife studio onboarding as completed."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
        settings.onboarding_completed = True
    return {"status": "ok"}


@router.post("/onboarding/reset")
async def reset_life_onboarding(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Reset ZugaLife studio onboarding so the user can replay it."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
        settings.onboarding_completed = False
    return {"status": "ok"}
