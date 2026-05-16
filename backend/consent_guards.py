"""ZugaLife consent guards — FastAPI dependencies that gate WRITE methods.

Pattern: attach to a router via `include_router(r, dependencies=[Depends(...)])`.
Read methods (GET, HEAD, OPTIONS) pass through so users can always review and
export their data; only writes require consent. Deletion endpoints live in
data_management.py which is intentionally ungated so revocation always works.

Two guards:
  require_health_consent  — mood / journal / habits / goals / meditation /
                            gamification writes (WA MHMDA + CA CMIA gate).
  require_health_and_ai   — therapist routes only (adds Venice AI sharing).
"""

import sys

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

_models = sys.modules["zugalife.models"]
LifeConsent = _models.LifeConsent

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


async def _load_consent(user_id: str):
    async with get_session() as session:
        return await session.scalar(
            select(LifeConsent).where(LifeConsent.user_id == user_id)
        )


def _missing_required(row, *, ai: bool) -> list[str]:
    """Return list of missing consent fields. Age is always required."""
    missing: list[str] = []
    if row is None or row.age_confirmed_at is None:
        missing.append("age_confirmed")
    if row is None or row.consent_health_collected_at is None:
        missing.append("health_collected")
    if ai and (row is None or row.consent_ai_sharing_at is None):
        missing.append("ai_sharing")
    return missing


async def require_health_consent(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    if request.method in _READ_METHODS:
        return
    missing = _missing_required(await _load_consent(user.id), ai=False)
    if missing:
        raise HTTPException(
            403,
            detail={
                "error": "consent_required",
                "missing": missing,
                "remedy": "POST /api/life/consent with the missing flags=true",
            },
        )


async def require_health_and_ai(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    if request.method in _READ_METHODS:
        return
    missing = _missing_required(await _load_consent(user.id), ai=True)
    if missing:
        raise HTTPException(
            403,
            detail={
                "error": "consent_required",
                "missing": missing,
                "remedy": "POST /api/life/consent with the missing flags=true",
            },
        )
