"""ZugaLife life goals database models."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin


class GoalDefinition(Base, TimestampMixin):
    """A life goal a user is working toward."""

    __tablename__ = "goal_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    template_key: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )

    milestones: Mapped[list["GoalMilestone"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GoalMilestone.sort_order",
    )

    habit_links: Mapped[list["GoalHabitLink"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class GoalMilestone(Base):
    """A sub-step / milestone within a life goal."""

    __tablename__ = "goal_milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("goal_definitions.id", ondelete="CASCADE"), index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    goal: Mapped["GoalDefinition"] = relationship(back_populates="milestones")


class GoalHabitLink(Base):
    """Many-to-many link between goals and habits."""

    __tablename__ = "goal_habit_links"
    __table_args__ = (
        UniqueConstraint("goal_id", "habit_id", name="uq_goal_habit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("goal_definitions.id", ondelete="CASCADE"), index=True,
    )
    habit_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    goal: Mapped["GoalDefinition"] = relationship(back_populates="habit_links")
