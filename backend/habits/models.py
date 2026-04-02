"""ZugaLife habit tracking database models."""

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin


class HabitDefinition(Base, TimestampMixin):
    """A habit a user wants to track (preset or custom)."""

    __tablename__ = "habit_definitions"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_habit_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    emoji: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    weekly_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger: Mapped[str | None] = mapped_column(String(200), nullable=True)


class HabitLog(Base, TimestampMixin):
    """A daily check-in for a specific habit.

    No foreign key to HabitDefinition — keeps historical data intact
    even if the habit definition is later deleted.
    """

    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "habit_id", "log_date",
            name="uq_habit_log_per_day",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    habit_id: Mapped[int] = mapped_column(Integer, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)


class HabitInsight(Base, TimestampMixin):
    """AI-generated weekly insight correlating habits with mood."""

    __tablename__ = "habit_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
