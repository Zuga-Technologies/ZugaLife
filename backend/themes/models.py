"""ZugaThemes database models — micro-app storage and marketplace."""

from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base, TimestampMixin


class Theme(Base, TimestampMixin):
    """A theme definition — the code + metadata for a micro-app."""

    __tablename__ = "themes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    creator_id: Mapped[str] = mapped_column(String(64), index=True)
    studio: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="widget")
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array

    # Code
    html: Mapped[str] = mapped_column(Text, nullable=False)
    css: Mapped[str | None] = mapped_column(Text, nullable=True)
    js: Mapped[str] = mapped_column(Text, nullable=False)
    permissions: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array

    version: Mapped[int] = mapped_column(Integer, default=1)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Marketplace
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    price_tokens: Mapped[int] = mapped_column(Integer, default=0)
    install_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_sum: Mapped[float] = mapped_column(Float, default=0.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    # Moderation
    status: Mapped[str] = mapped_column(String(20), default="draft")
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ThemeInstall(Base, TimestampMixin):
    """A user's installed theme instance in a studio."""

    __tablename__ = "theme_installs"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_id", name="uq_theme_install_user_theme"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    theme_id: Mapped[str] = mapped_column(String(36), index=True)
    studio: Mapped[str] = mapped_column(String(50), nullable=False)

    # Grid position (user can drag/resize)
    pos_x: Mapped[int] = mapped_column(Integer, default=0)
    pos_y: Mapped[int] = mapped_column(Integer, default=0)
    pos_w: Mapped[int] = mapped_column(Integer, default=6)
    pos_h: Mapped[int] = mapped_column(Integer, default=4)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ThemeState(Base, TimestampMixin):
    """Theme-private persistent state — per user, per theme."""

    __tablename__ = "theme_states"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_id", name="uq_theme_state_user_theme"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    theme_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ThemePurchase(Base, TimestampMixin):
    """Marketplace transaction record."""

    __tablename__ = "theme_purchases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    buyer_id: Mapped[str] = mapped_column(String(64), index=True)
    seller_id: Mapped[str] = mapped_column(String(64), index=True)
    theme_id: Mapped[str] = mapped_column(String(36), index=True)
    price_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_cut: Mapped[int] = mapped_column(Integer, nullable=False)
    creator_cut: Mapped[int] = mapped_column(Integer, nullable=False)


class ThemeReview(Base, TimestampMixin):
    """User review/rating for a theme."""

    __tablename__ = "theme_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_id", name="uq_theme_review_user_theme"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    theme_id: Mapped[str] = mapped_column(String(36), index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    review_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
