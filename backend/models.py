"""ZugaLife mood entry + consent models."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin


class MoodEntry(Base, TimestampMixin):
    __tablename__ = "mood_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    emoji: Mapped[str] = mapped_column(String(4))
    label: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LifeConsent(Base, TimestampMixin):
    """Per-user consent record for ZugaLife.

    consent_health_collected_at — WA MHMDA + CA CMIA opt-in for collection of
        mood / journal / habit / wellness data.
    consent_ai_sharing_at — opt-in to share mental-health conversations with
        Venice AI for the therapist feature.
    deletion_requested_at — set when user requests full account deletion;
        actual purge runs immediately, this stamp anchors the 30-day SLA window
        we promise users.

    One row per user_id. Inserted on first POST /api/life/consent.
    """

    __tablename__ = "life_consents"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consent_health_collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_ai_sharing_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # COPPA gate — stamped when user affirms 13+ at signup. One under-13 user
    # triggers strict liability, so this MUST be set before any data collection.
    age_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Versioned consent — bump backend CURRENT_CONSENT_VERSION when consent
    # copy materially changes (e.g., Mike's T1/T2/T3 final language lands).
    # Users whose stamped version < CURRENT are forced through the onboarding
    # consent gate again. See backend/consent_constants.py.
    consent_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
