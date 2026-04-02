"""ZugaLife journal entry and reflection database models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin


class JournalEntry(Base, TimestampMixin):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    mood_emoji: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mood_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated

    reflections: Mapped[list["JournalReflection"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class JournalReflection(Base):
    __tablename__ = "journal_reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("journal_entries.id", ondelete="CASCADE"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(50))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    entry: Mapped["JournalEntry"] = relationship(back_populates="reflections")
