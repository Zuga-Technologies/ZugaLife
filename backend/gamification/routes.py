"""ZugaLife gamification endpoints — XP status, badges, daily challenges, and award."""

import sys
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.gamification.models"]
_schemas = sys.modules["zugalife.gamification.schemas"]
_engine = sys.modules["zugalife.gamification.engine"]

UserXP = _models.UserXP
XPTransaction = _models.XPTransaction
UserBadge = _models.UserBadge
DailyChallenge = _models.DailyChallenge

GamificationDashboard = _schemas.GamificationDashboard
XPStatusResponse = _schemas.XPStatusResponse
XPGainResponse = _schemas.XPGainResponse
BadgeResponse = _schemas.BadgeResponse
DailyChallengeResponse = _schemas.DailyChallengeResponse
AwardXPRequest = _schemas.AwardXPRequest

router = APIRouter(prefix="/api/life/gamification", tags=["life-gamification"])


@router.get("", response_model=GamificationDashboard)
async def get_gamification_dashboard(
    user: CurrentUser = Depends(get_current_user),
):
    """Full gamification status — XP, badges, recent transactions, and today's challenges."""
    async with get_session() as session:
        xp_status = await _engine.build_xp_status(session, user.id)

        # Badges — join with metadata from BADGES dict
        badges_result = await session.execute(
            select(UserBadge)
            .where(UserBadge.user_id == user.id)
            .order_by(UserBadge.earned_at)
        )
        badge_rows = badges_result.scalars().all()
        badges = [
            _engine.build_badge_response(b.badge_key, earned_at=b.earned_at)
            for b in badge_rows
        ]

        # Recent XP transactions (last 10)
        tx_result = await session.execute(
            select(XPTransaction)
            .where(XPTransaction.user_id == user.id)
            .order_by(desc(XPTransaction.created_at))
            .limit(10)
        )
        tx_rows = tx_result.scalars().all()
        recent_xp = [
            {
                "amount": tx.amount,
                "source": tx.source,
                "description": tx.description,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in tx_rows
        ]

        # Daily challenges — ensure generated, then fetch
        challenge_rows = await _engine.ensure_daily_challenges(session, user.id)
        challenges = [
            DailyChallengeResponse(
                challenge_key=c.challenge_key,
                title=c.title,
                description=c.description,
                xp_reward=c.xp_reward,
                is_completed=c.is_completed,
            )
            for c in challenge_rows
        ]

    return GamificationDashboard(
        xp=xp_status,
        badges=badges,
        recent_xp=recent_xp,
        daily_challenges=challenges,
    )


@router.get("/xp", response_model=XPStatusResponse)
async def get_xp_status(
    user: CurrentUser = Depends(get_current_user),
):
    """Current XP, level, streak, and progress toward next level."""
    async with get_session() as session:
        return await _engine.build_xp_status(session, user.id)


@router.get("/badges", response_model=list[BadgeResponse])
async def get_badges(
    user: CurrentUser = Depends(get_current_user),
):
    """All badges earned by this user, enriched with badge metadata."""
    async with get_session() as session:
        result = await session.execute(
            select(UserBadge)
            .where(UserBadge.user_id == user.id)
            .order_by(UserBadge.earned_at)
        )
        rows = result.scalars().all()
    return [
        _engine.build_badge_response(b.badge_key, earned_at=b.earned_at)
        for b in rows
    ]


@router.get("/challenges", response_model=list[DailyChallengeResponse])
async def get_daily_challenges(
    user: CurrentUser = Depends(get_current_user),
):
    """Today's daily challenges for this user (generated on first request)."""
    async with get_session() as session:
        rows = await _engine.ensure_daily_challenges(session, user.id)
    return [
        DailyChallengeResponse(
            challenge_key=c.challenge_key,
            title=c.title,
            description=c.description,
            xp_reward=c.xp_reward,
            is_completed=c.is_completed,
        )
        for c in rows
    ]


@router.post("/award", response_model=XPGainResponse)
async def award_xp(
    body: AwardXPRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Award XP to the authenticated user.

    This endpoint is intended for internal calls from other ZugaLife modules
    and for testing.  The source must be a known XP_TABLE key or 'streak_bonus'.

    Valid sources: mood_log, habit_check, journal_entry, meditation_complete,
    therapist_session, goal_milestone, daily_challenge, streak_bonus.
    """
    valid_sources = set(_engine.XP_TABLE.keys())
    if body.source not in valid_sources:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown source '{body.source}'. Valid: {sorted(valid_sources)}",
        )

    async with get_session() as session:
        result = await _engine.award_xp(
            session,
            user_id=user.id,
            source=body.source,
            description=body.description,
            base_amount=body.base_amount,
        )
    return result
