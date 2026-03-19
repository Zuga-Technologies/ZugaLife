"""ZugaLife per-user settings model.

One row per user. Auto-created with defaults on first GET.
Each studio owns its own settings table — no cross-studio sharing.
"""

from sqlalchemy import Float, Integer, String
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

    # Meditation defaults
    med_duration: Mapped[int] = mapped_column(Integer, default=10)
    med_voice: Mapped[str] = mapped_column(String(20), default="nova")
    med_ambience: Mapped[str] = mapped_column(String(20), default="rain")
