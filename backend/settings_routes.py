"""ZugaLife user settings endpoints.

GET  /api/life/settings  → return current settings (auto-create if missing)
PUT  /api/life/settings  → upsert settings (partial update)
GET  /api/life/settings/personalization → Zugabot/user personalization config
PATCH /api/life/settings/personalization → update personalization (Zugabot or user)
POST /api/life/internal/apply-theme → service-to-service theme application (Zugabot → ZugaLife)
"""

import json
import logging
import os
import sys

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

logger = logging.getLogger(__name__)

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

_models = sys.modules["zugalife.settings_models"]
_schemas = sys.modules["zugalife.settings_schemas"]

LifeUserSettings = _models.LifeUserSettings
LifeSettingsResponse = _schemas.LifeSettingsResponse
LifeSettingsUpdate = _schemas.LifeSettingsUpdate
VALID_THEMES = _schemas.VALID_THEMES
VALID_THEME_PRESETS = _schemas.VALID_THEME_PRESETS
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
        if "theme_preset" in updates and updates["theme_preset"] not in VALID_THEME_PRESETS:
            raise HTTPException(400, f"Invalid theme preset. Allowed: {sorted(VALID_THEME_PRESETS)}")

        # Validate timezone
        if "timezone" in updates:
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(updates["timezone"])
            except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                raise HTTPException(400, f"Invalid timezone: {updates['timezone']}")

        for field, value in updates.items():
            setattr(settings, field, value)

        # Sync display_name to core UserRecord so it's available in auth, chat, nav
        if "display_name" in updates and updates["display_name"]:
            try:
                from core.auth.models import UserRecord
                user_result = await session.execute(
                    select(UserRecord).where(UserRecord.id == user.id)
                )
                user_record = user_result.scalar_one_or_none()
                if user_record:
                    user_record.name = updates["display_name"]
            except Exception:
                pass  # Non-critical — Life settings still saved

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


# ── Daily breath cold-open (cross-device gate) ──────────────────


@router.get("/breath/today")
async def get_breath_today(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return whether the user has completed today's breath ritual on any device.

    "Today" is in the user's configured timezone — so rollover happens at the
    user's midnight, not UTC's. Otherwise the prompt re-appears at 8pm EDT
    (UTC midnight) instead of true local midnight.
    """
    import sys
    _helpers = sys.modules["zugalife.settings_helpers"]
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
        today_iso = (await _helpers.get_user_today(session, user.id)).isoformat()
        return {
            "done_today": settings.last_breath_date == today_iso,
            "last_breath_date": settings.last_breath_date,
        }


@router.post("/breath/done")
async def mark_breath_done(
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Mark today's breath ritual complete. Idempotent — safe to call repeatedly."""
    import sys
    _helpers = sys.modules["zugalife.settings_helpers"]
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
        today_iso = (await _helpers.get_user_today(session, user.id)).isoformat()
        settings.last_breath_date = today_iso
    return {"status": "ok", "last_breath_date": today_iso}


# ── Zugabot Personalization Layer ────────────────────────────────


VALID_PLAYER_TYPES = {"achiever", "explorer", "socializer"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_SOURCES = {"user", "zugabot", "system"}


class PersonalizationResponse(BaseModel):
    player_type: str
    challenge_difficulty: str
    gamification_emphasis: float
    personalization_source: str


class PersonalizationUpdate(BaseModel):
    player_type: str | None = Field(None, description="achiever|explorer|socializer")
    challenge_difficulty: str | None = Field(None, description="easy|medium|hard")
    gamification_emphasis: float | None = Field(None, ge=0.0, le=1.0)
    source: str | None = Field(None, description="user|zugabot")


@router.get("/settings/personalization", response_model=PersonalizationResponse)
async def get_personalization(
    user: CurrentUser = Depends(get_current_user),
):
    """Get current personalization config (readable by frontend and Zugabot)."""
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)
    return PersonalizationResponse(
        player_type=settings.player_type or "achiever",
        challenge_difficulty=settings.challenge_difficulty or "medium",
        gamification_emphasis=settings.gamification_emphasis if settings.gamification_emphasis is not None else 0.7,
        personalization_source=settings.personalization_source or "system",
    )


@router.patch("/settings/personalization", response_model=PersonalizationResponse)
async def update_personalization(
    body: PersonalizationUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Update personalization config. Writable by both the user and Zugabot agent.

    Zugabot can learn which gamification style works for each user (Bartle player types)
    and adjust challenge difficulty in real-time (Csikszentmihalyi's flow channel).
    """
    async with get_session() as session:
        settings = await _get_or_create_settings(session, user.id)

        if body.player_type is not None:
            if body.player_type not in VALID_PLAYER_TYPES:
                raise HTTPException(400, f"Invalid player_type. Allowed: {sorted(VALID_PLAYER_TYPES)}")
            settings.player_type = body.player_type

        if body.challenge_difficulty is not None:
            if body.challenge_difficulty not in VALID_DIFFICULTIES:
                raise HTTPException(400, f"Invalid difficulty. Allowed: {sorted(VALID_DIFFICULTIES)}")
            settings.challenge_difficulty = body.challenge_difficulty

        if body.gamification_emphasis is not None:
            settings.gamification_emphasis = body.gamification_emphasis

        settings.personalization_source = body.source or "user"

        await session.flush()
        await session.refresh(settings)

    return PersonalizationResponse(
        player_type=settings.player_type,
        challenge_difficulty=settings.challenge_difficulty,
        gamification_emphasis=settings.gamification_emphasis,
        personalization_source=settings.personalization_source,
    )


# ── Internal Service Endpoint (Zugabot → ZugaLife) ─────────────────


_SERVICE_KEY = os.environ.get("ZUGABOT_SERVICE_KEY", "")


class InternalThemeRequest(BaseModel):
    user_id: str = Field(..., description="Target user ID")
    custom_colors: str = Field(..., description="JSON string with css + name + font")
    theme_preset: str | None = Field(None, description="Optional preset ID to set")


@router.post("/internal/apply-theme")
async def internal_apply_theme(
    body: InternalThemeRequest,
    x_service_key: str = Header(alias="X-Service-Key", default=""),
):
    """Service-to-service endpoint for Zugabot to apply themes.

    Now forwards to ZugaApp's theme override system instead of writing
    to custom_colors. This ensures themes show in Settings > My Themes
    and can be scoped to any studio.
    """
    if not _SERVICE_KEY or x_service_key != _SERVICE_KEY:
        raise HTTPException(403, "Invalid service key")

    # Parse the custom_colors JSON to extract CSS, name, font
    try:
        parsed = json.loads(body.custom_colors)
        css = parsed.get("css", "")
        name = parsed.get("name", "Custom Theme")
        font = parsed.get("font")
    except (json.JSONDecodeError, AttributeError):
        raise HTTPException(400, "custom_colors must be valid JSON with a 'css' field")

    if not css:
        raise HTTPException(400, "No CSS found in custom_colors")

    # Forward to ZugaApp's theme override API (scope=life by default)
    zugaapp_url = os.environ.get("ZUGAAPP_INTERNAL_URL", "http://localhost:8000")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{zugaapp_url}/api/theme/internal/apply",
                json={
                    "user_id": body.user_id,
                    "scope": "life",
                    "css_override": css,
                    "theme_name": name,
                    "font": font,
                },
                headers={"X-Service-Key": _SERVICE_KEY},
            )
            if resp.status_code != 200:
                logger.warning(f"[Theme] ZugaApp override API returned {resp.status_code}: {resp.text[:200]}")
                raise HTTPException(502, "Failed to apply theme via override system")
    except httpx.HTTPError as e:
        logger.error(f"[Theme] Failed to reach ZugaApp: {e}")
        raise HTTPException(502, "Could not reach ZugaApp theme API")

    # Also apply preset if specified
    if body.theme_preset and body.theme_preset in VALID_THEME_PRESETS:
        async with get_session() as session:
            settings = await _get_or_create_settings(session, body.user_id)
            settings.theme_preset = body.theme_preset

    return {"status": "ok", "user_id": body.user_id, "applied": True}
