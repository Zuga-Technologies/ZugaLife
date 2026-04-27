"""ZugaLife per-user settings model.

One row per user. Auto-created with defaults on first GET.
Each studio owns its own settings table — no cross-studio sharing.
"""

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin


class LifeUserSettings(Base, TimestampMixin):
    __tablename__ = "life_user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Display
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    theme: Mapped[str] = mapped_column(String(30), default="default-dark")
    theme_opacity: Mapped[float] = mapped_column(Float, default=0.3)
    theme_preset: Mapped[str] = mapped_column(String(30), default="default")

    # Meditation defaults
    med_length: Mapped[str] = mapped_column(String(10), default="medium")
    med_duration: Mapped[str | None] = mapped_column(String(10), nullable=True, default="medium")  # legacy column — kept for DB compat
    med_voice: Mapped[str] = mapped_column(String(20), default="nova")
    med_ambience: Mapped[str] = mapped_column(String(20), default="rain")

    # Onboarding
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Daily breath cold-open — ISO date string of last completion (YYYY-MM-DD).
    # Stored as string to avoid migration headaches with Date column on SQLite.
    # Used to gate the breath ritual cross-device (mobile + desktop share state).
    last_breath_date: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Custom studio colors (JSON: {"colors": {...}, "css": "..."})
    custom_colors: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Zugabot personalization layer (Bartle player types + adaptive difficulty)
    # These fields are writable by both the user and Zugabot agent
    player_type: Mapped[str] = mapped_column(String(20), default="achiever")  # achiever|explorer|socializer
    challenge_difficulty: Mapped[str] = mapped_column(String(10), default="medium")  # easy|medium|hard
    gamification_emphasis: Mapped[float] = mapped_column(Float, default=0.7)  # 0.0=intrinsic only, 1.0=full gamification
    personalization_source: Mapped[str] = mapped_column(String(10), default="system")  # user|zugabot|system
