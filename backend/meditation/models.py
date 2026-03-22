"""ZugaLife meditation session database model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base


class MeditationSession(Base):
    """A generated meditation session."""

    __tablename__ = "meditation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)

    # Session config
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    length: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ambience: Mapped[str] = mapped_column(String(20), nullable=False)
    voice: Mapped[str] = mapped_column(String(20), nullable=False, default="shimmer")
    focus: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Generated content
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    audio_filename: Mapped[str] = mapped_column(String(200), nullable=False)

    # AI metadata
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    tts_model: Mapped[str] = mapped_column(String(50), nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0)

    # User interaction
    mood_before: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mood_after: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
