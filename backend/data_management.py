"""ZugaLife data management endpoints — per-module and full reset.

All endpoints require authentication. Each reset is scoped strictly to the
authenticated user's data. Settings are intentionally excluded from reset-all.

Meditation audio cleanup uses shutil.rmtree on the per-user audio directory —
safe because the directory path is constructed from user.id (server-controlled),
never from user input.
"""

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Models loaded via sys.modules (plugin.py pre-loads them)
_models = sys.modules["zugalife.models"]
_j_models = sys.modules["zugalife.journal.models"]
_h_models = sys.modules["zugalife.habits.models"]
_g_models = sys.modules["zugalife.goals.models"]
_m_models = sys.modules["zugalife.meditation.models"]
_t_models = sys.modules["zugalife.therapist.models"]
_gam_models = sys.modules["zugalife.gamification.models"]

MoodEntry = _models.MoodEntry
LifeConsent = _models.LifeConsent
JournalEntry = _j_models.JournalEntry
HabitDefinition = _h_models.HabitDefinition
HabitLog = _h_models.HabitLog
HabitInsight = _h_models.HabitInsight
GoalDefinition = _g_models.GoalDefinition
MeditationSession = _m_models.MeditationSession
TherapistSessionNote = _t_models.TherapistSessionNote
UserXP = _gam_models.UserXP
XPTransaction = _gam_models.XPTransaction
UserBadge = _gam_models.UserBadge
DailyChallenge = _gam_models.DailyChallenge

router = APIRouter(prefix="/api/life/data", tags=["life-data-management"])

# Meditation audio is stored relative to this file's parent directory
_AUDIO_BASE = Path(__file__).parent / "data" / "meditation_audio"


# ---------------------------------------------------------------------------
# Individual reset endpoints
# ---------------------------------------------------------------------------


@router.delete("/reset/mood", status_code=200)
async def reset_mood(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all mood entries for this user."""
    async with get_session() as session:
        result = await session.execute(
            delete(MoodEntry)
            .where(MoodEntry.user_id == user.id)
            .returning(MoodEntry.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/habits", status_code=200)
async def reset_habits(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all habit logs, insights, and definitions for this user.

    This is a full wipe — custom habits are removed along with all history.
    Preset habits will be re-seeded automatically on the next visit to the
    habits page.
    """
    async with get_session() as session:
        logs_result = await session.execute(
            delete(HabitLog)
            .where(HabitLog.user_id == user.id)
            .returning(HabitLog.id)
        )
        insights_result = await session.execute(
            delete(HabitInsight)
            .where(HabitInsight.user_id == user.id)
            .returning(HabitInsight.id)
        )
        defs_result = await session.execute(
            delete(HabitDefinition)
            .where(HabitDefinition.user_id == user.id)
            .returning(HabitDefinition.id)
        )
        count = (
            len(logs_result.all())
            + len(insights_result.all())
            + len(defs_result.all())
        )
    return {"deleted": count}


@router.delete("/reset/goals", status_code=200)
async def reset_goals(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all goal definitions for this user.

    Milestones and habit links are removed automatically via FK cascade delete.
    """
    async with get_session() as session:
        result = await session.execute(
            delete(GoalDefinition)
            .where(GoalDefinition.user_id == user.id)
            .returning(GoalDefinition.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/journal", status_code=200)
async def reset_journal(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all journal entries for this user.

    Reflections are removed automatically via FK cascade delete.
    """
    async with get_session() as session:
        result = await session.execute(
            delete(JournalEntry)
            .where(JournalEntry.user_id == user.id)
            .returning(JournalEntry.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/meditation", status_code=200)
async def reset_meditation(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all meditation sessions for this user and remove their audio files.

    Audio files live at data/meditation_audio/{user_id}/. The entire directory
    is removed with shutil.rmtree. The path is constructed server-side from
    user.id — no user input touches the filesystem path.
    """
    async with get_session() as session:
        result = await session.execute(
            delete(MeditationSession)
            .where(MeditationSession.user_id == user.id)
            .returning(MeditationSession.id)
        )
        count = len(result.all())

    # Remove audio files after the DB transaction commits
    audio_dir = _AUDIO_BASE / user.id
    if audio_dir.is_dir():
        shutil.rmtree(audio_dir)

    return {"deleted": count}


@router.delete("/reset/therapist", status_code=200)
async def reset_therapist(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all therapist session notes for this user."""
    async with get_session() as session:
        result = await session.execute(
            delete(TherapistSessionNote)
            .where(TherapistSessionNote.user_id == user.id)
            .returning(TherapistSessionNote.id)
        )
        count = len(result.all())
    return {"deleted": count}


@router.delete("/reset/gamification", status_code=200)
async def reset_gamification(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all gamification data (XP, transactions, badges, challenges) for this user."""
    async with get_session() as session:
        xp_result = await session.execute(
            delete(UserXP)
            .where(UserXP.user_id == user.id)
            .returning(UserXP.id)
        )
        tx_result = await session.execute(
            delete(XPTransaction)
            .where(XPTransaction.user_id == user.id)
            .returning(XPTransaction.id)
        )
        badges_result = await session.execute(
            delete(UserBadge)
            .where(UserBadge.user_id == user.id)
            .returning(UserBadge.id)
        )
        challenges_result = await session.execute(
            delete(DailyChallenge)
            .where(DailyChallenge.user_id == user.id)
            .returning(DailyChallenge.id)
        )
        count = (
            len(xp_result.all())
            + len(tx_result.all())
            + len(badges_result.all())
            + len(challenges_result.all())
        )
    return {"deleted": count}


# ---------------------------------------------------------------------------
# Full reset (all modules except settings)
# ---------------------------------------------------------------------------


@router.delete("/reset/all", status_code=200)
async def reset_all(
    user: CurrentUser = Depends(get_current_user),
):
    """Delete all ZugaLife data for this user across every module.

    Settings are intentionally preserved — the user keeps their timezone,
    theme, voice, and ambience preferences after a data reset.

    Returns per-module deleted counts plus a combined total.
    """
    async with get_session() as session:
        mood_result = await session.execute(
            delete(MoodEntry)
            .where(MoodEntry.user_id == user.id)
            .returning(MoodEntry.id)
        )
        mood_count = len(mood_result.all())

        logs_result = await session.execute(
            delete(HabitLog)
            .where(HabitLog.user_id == user.id)
            .returning(HabitLog.id)
        )
        insights_result = await session.execute(
            delete(HabitInsight)
            .where(HabitInsight.user_id == user.id)
            .returning(HabitInsight.id)
        )
        defs_result = await session.execute(
            delete(HabitDefinition)
            .where(HabitDefinition.user_id == user.id)
            .returning(HabitDefinition.id)
        )
        habits_count = (
            len(logs_result.all())
            + len(insights_result.all())
            + len(defs_result.all())
        )

        goals_result = await session.execute(
            delete(GoalDefinition)
            .where(GoalDefinition.user_id == user.id)
            .returning(GoalDefinition.id)
        )
        goals_count = len(goals_result.all())

        journal_result = await session.execute(
            delete(JournalEntry)
            .where(JournalEntry.user_id == user.id)
            .returning(JournalEntry.id)
        )
        journal_count = len(journal_result.all())

        med_result = await session.execute(
            delete(MeditationSession)
            .where(MeditationSession.user_id == user.id)
            .returning(MeditationSession.id)
        )
        meditation_count = len(med_result.all())

        therapist_result = await session.execute(
            delete(TherapistSessionNote)
            .where(TherapistSessionNote.user_id == user.id)
            .returning(TherapistSessionNote.id)
        )
        therapist_count = len(therapist_result.all())

        gam_xp_result = await session.execute(
            delete(UserXP)
            .where(UserXP.user_id == user.id)
            .returning(UserXP.id)
        )
        gam_tx_result = await session.execute(
            delete(XPTransaction)
            .where(XPTransaction.user_id == user.id)
            .returning(XPTransaction.id)
        )
        gam_badges_result = await session.execute(
            delete(UserBadge)
            .where(UserBadge.user_id == user.id)
            .returning(UserBadge.id)
        )
        gam_challenges_result = await session.execute(
            delete(DailyChallenge)
            .where(DailyChallenge.user_id == user.id)
            .returning(DailyChallenge.id)
        )
        gamification_count = (
            len(gam_xp_result.all())
            + len(gam_tx_result.all())
            + len(gam_badges_result.all())
            + len(gam_challenges_result.all())
        )

    # Remove meditation audio after DB transaction commits
    audio_dir = _AUDIO_BASE / user.id
    if audio_dir.is_dir():
        shutil.rmtree(audio_dir)

    total = (
        mood_count
        + habits_count
        + goals_count
        + journal_count
        + meditation_count
        + therapist_count
        + gamification_count
    )

    return {
        "deleted": {
            "mood": mood_count,
            "habits": habits_count,
            "goals": goals_count,
            "journal": journal_count,
            "meditation": meditation_count,
            "therapist": therapist_count,
            "gamification": gamification_count,
            "total": total,
        }
    }


# ---------------------------------------------------------------------------
# Consent (WA MHMDA + CA CMIA — opt-in must occur BEFORE any health data
# collection. UI gates the first onboarding step on this; routes that collect
# health data should also guard via require_health_consent / require_ai_consent
# in a follow-up pass.)
# ---------------------------------------------------------------------------


_consent_router = APIRouter(prefix="/api/life/consent", tags=["life-consent"])


class ConsentBody(BaseModel):
    health_collected: bool = False
    ai_sharing: bool = False
    age_confirmed: bool = False  # COPPA — user affirms they are 13+


class ConsentState(BaseModel):
    health_collected_at: datetime | None
    ai_sharing_at: datetime | None
    age_confirmed_at: datetime | None
    deletion_requested_at: datetime | None


@_consent_router.get("", response_model=ConsentState)
async def get_consent(user: CurrentUser = Depends(get_current_user)) -> ConsentState:
    async with get_session() as session:
        row = await session.scalar(
            select(LifeConsent).where(LifeConsent.user_id == user.id)
        )
    if row is None:
        return ConsentState(
            health_collected_at=None,
            ai_sharing_at=None,
            age_confirmed_at=None,
            deletion_requested_at=None,
        )
    return ConsentState(
        health_collected_at=row.consent_health_collected_at,
        ai_sharing_at=row.consent_ai_sharing_at,
        age_confirmed_at=row.age_confirmed_at,
        deletion_requested_at=row.deletion_requested_at,
    )


@_consent_router.post("", response_model=ConsentState)
async def record_consent(
    body: ConsentBody,
    user: CurrentUser = Depends(get_current_user),
) -> ConsentState:
    """Stamp consent timestamps. Idempotent: re-posting only stamps fields that
    haven't been stamped yet — consent can be GIVEN but never silently revoked
    through this endpoint. (Revocation runs through DELETE /api/life/users/me.)
    """
    if not (body.health_collected or body.ai_sharing or body.age_confirmed):
        raise HTTPException(400, "at least one consent flag must be true")

    now = datetime.now(timezone.utc)
    async with get_session() as session:
        stmt = (
            sqlite_insert(LifeConsent)
            .values(
                user_id=user.id,
                consent_health_collected_at=now if body.health_collected else None,
                consent_ai_sharing_at=now if body.ai_sharing else None,
                age_confirmed_at=now if body.age_confirmed else None,
            )
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await session.execute(stmt)

        row = await session.scalar(
            select(LifeConsent).where(LifeConsent.user_id == user.id)
        )
        # Stamp only fields not yet set so we preserve original consent dates
        if body.health_collected and row.consent_health_collected_at is None:
            row.consent_health_collected_at = now
        if body.ai_sharing and row.consent_ai_sharing_at is None:
            row.consent_ai_sharing_at = now
        if body.age_confirmed and row.age_confirmed_at is None:
            row.age_confirmed_at = now

    return ConsentState(
        health_collected_at=row.consent_health_collected_at,
        ai_sharing_at=row.consent_ai_sharing_at,
        age_confirmed_at=row.age_confirmed_at,
        deletion_requested_at=row.deletion_requested_at,
    )


router.include_router(_consent_router)


# ---------------------------------------------------------------------------
# Account deletion (WA MHMDA 45d / GDPR 30d / FTC HBNR — we promise 30d SLA)
# ---------------------------------------------------------------------------


_user_router = APIRouter(prefix="/api/life/users", tags=["life-users"])


class DeleteResponse(BaseModel):
    status: str
    deletion_requested_at: datetime
    sla_days: int
    purged: dict


@_user_router.delete("/me", response_model=DeleteResponse, status_code=200)
async def delete_me(user: CurrentUser = Depends(get_current_user)) -> DeleteResponse:
    """Full ZugaLife account deletion.

    Runs the same per-module purge as /api/life/data/reset/all and stamps
    deletion_requested_at on the user's consent record. The stamp is the
    SLA anchor — any latent caches / logs / backups must be purged within
    30 days of that timestamp.
    """
    purged: dict[str, int] = {}
    requested_at = datetime.now(timezone.utc)

    async with get_session() as session:
        # ---- Mood
        r = await session.execute(
            delete(MoodEntry).where(MoodEntry.user_id == user.id).returning(MoodEntry.id)
        )
        purged["mood"] = len(r.all())

        # ---- Habits
        h_logs = await session.execute(
            delete(HabitLog).where(HabitLog.user_id == user.id).returning(HabitLog.id)
        )
        h_ins = await session.execute(
            delete(HabitInsight).where(HabitInsight.user_id == user.id).returning(HabitInsight.id)
        )
        h_def = await session.execute(
            delete(HabitDefinition).where(HabitDefinition.user_id == user.id).returning(HabitDefinition.id)
        )
        purged["habits"] = len(h_logs.all()) + len(h_ins.all()) + len(h_def.all())

        # ---- Goals
        g = await session.execute(
            delete(GoalDefinition).where(GoalDefinition.user_id == user.id).returning(GoalDefinition.id)
        )
        purged["goals"] = len(g.all())

        # ---- Journal
        j = await session.execute(
            delete(JournalEntry).where(JournalEntry.user_id == user.id).returning(JournalEntry.id)
        )
        purged["journal"] = len(j.all())

        # ---- Meditation
        m = await session.execute(
            delete(MeditationSession).where(MeditationSession.user_id == user.id).returning(MeditationSession.id)
        )
        purged["meditation"] = len(m.all())

        # ---- Therapist
        t = await session.execute(
            delete(TherapistSessionNote).where(TherapistSessionNote.user_id == user.id).returning(TherapistSessionNote.id)
        )
        purged["therapist"] = len(t.all())

        # ---- Gamification
        xp = await session.execute(
            delete(UserXP).where(UserXP.user_id == user.id).returning(UserXP.id)
        )
        tx = await session.execute(
            delete(XPTransaction).where(XPTransaction.user_id == user.id).returning(XPTransaction.id)
        )
        ub = await session.execute(
            delete(UserBadge).where(UserBadge.user_id == user.id).returning(UserBadge.id)
        )
        dc = await session.execute(
            delete(DailyChallenge).where(DailyChallenge.user_id == user.id).returning(DailyChallenge.id)
        )
        purged["gamification"] = (
            len(xp.all()) + len(tx.all()) + len(ub.all()) + len(dc.all())
        )

        # ---- Stamp deletion request on consent row (insert if user never
        # consented but is somehow requesting deletion — extreme edge case)
        stmt = (
            sqlite_insert(LifeConsent)
            .values(user_id=user.id, deletion_requested_at=requested_at)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await session.execute(stmt)
        row = await session.scalar(
            select(LifeConsent).where(LifeConsent.user_id == user.id)
        )
        row.deletion_requested_at = requested_at

    # Audio cleanup post-commit (same pattern as reset_all)
    audio_dir = _AUDIO_BASE / user.id
    if audio_dir.is_dir():
        shutil.rmtree(audio_dir)

    purged["total"] = sum(v for k, v in purged.items() if k != "total")

    return DeleteResponse(
        status="purged",
        deletion_requested_at=requested_at,
        sla_days=30,
        purged=purged,
    )


router.include_router(_user_router)
