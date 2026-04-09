"""ZugaLife ecosystem integration — receives behavioral signals from other ZugaApp studios.

No competitor has cross-app behavioral data. Finch knows your habits. Calm knows your
meditation. ZugaLife can know your habits AND that you were gaming until 3am (ZugaGamer)
or had a stressful trading day (ZugaTrader). That's a whole-person picture.

This module:
1. Subscribes to the ZugaApp event bus
2. Filters for cross-studio signals relevant to wellness
3. Stores them in CrossStudioSignal table
4. Makes them available to therapist context and challenge generation
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, func, select, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class CrossStudioSignal(Base):
    """A behavioral signal received from another ZugaApp studio."""

    __tablename__ = "life_cross_studio_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    source_studio: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Inbound event mapping — which events we care about and how to summarize
# ---------------------------------------------------------------------------

INBOUND_EVENTS: dict[str, dict] = {
    "gamer:session_ended": {
        "studio": "ZugaGamer",
        "summarize": lambda d: (
            f"Gaming session ended at {d.get('ended_at', 'unknown time')}"
            f" ({d.get('game', 'unknown game')}, {d.get('duration_minutes', '?')} min)"
        ),
        "wellness_impact": "sleep/activity",
    },
    "trader:session_ended": {
        "studio": "ZugaTrader",
        "summarize": lambda d: (
            f"Trading session ended"
            f" (P&L: {d.get('pnl', 'unknown')}, stress: {d.get('stress_level', 'unknown')})"
        ),
        "wellness_impact": "stress/mood",
    },
    "gamer:late_session": {
        "studio": "ZugaGamer",
        "summarize": lambda d: (
            f"Late-night gaming detected at {d.get('time', 'unknown')}"
            f" ({d.get('game', 'unknown game')})"
        ),
        "wellness_impact": "sleep",
    },
    "trader:high_stress": {
        "studio": "ZugaTrader",
        "summarize": lambda d: (
            f"High-stress trading event: {d.get('reason', 'unknown')}"
        ),
        "wellness_impact": "stress/mood",
    },
}


# ---------------------------------------------------------------------------
# Event handler (registered on event bus at startup)
# ---------------------------------------------------------------------------

async def handle_ecosystem_event(event: dict) -> None:
    """Process an inbound event from the ZugaApp event bus.

    Only stores events that match our INBOUND_EVENTS mapping.
    """
    event_type = event.get("type", "")
    if event_type not in INBOUND_EVENTS:
        return

    user_id = event.get("user_id")
    if not user_id:
        return

    config = INBOUND_EVENTS[event_type]
    data = event.get("data", {})

    try:
        import json
        from core.database.session import get_session

        summary = config["summarize"](data)

        async with get_session() as session:
            signal = CrossStudioSignal(
                user_id=user_id,
                source_studio=config["studio"],
                event_type=event_type,
                summary=summary,
                raw_data=json.dumps(data),
            )
            session.add(signal)

        logger.info(
            "Ecosystem signal stored: %s for user %s — %s",
            event_type, user_id[:8], summary[:80],
        )
    except Exception:
        logger.warning("Failed to store ecosystem signal: %s", event_type, exc_info=True)


# ---------------------------------------------------------------------------
# Query helpers (used by therapist context and challenge generation)
# ---------------------------------------------------------------------------

async def get_recent_signals(session, user_id: str, days: int = 7, limit: int = 5) -> list[dict]:
    """Get recent cross-studio signals for a user.

    Returns list of {source_studio, event_type, summary, received_at} dicts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(CrossStudioSignal)
        .where(
            CrossStudioSignal.user_id == user_id,
            CrossStudioSignal.received_at >= cutoff,
        )
        .order_by(CrossStudioSignal.received_at.desc())
        .limit(limit)
    )
    signals = result.scalars().all()
    return [
        {
            "source_studio": s.source_studio,
            "event_type": s.event_type,
            "summary": s.summary,
            "received_at": s.received_at.isoformat() if s.received_at else None,
        }
        for s in signals
    ]


def register_event_handler() -> None:
    """Register the ecosystem event handler with the ZugaApp event bus.

    Called during plugin startup. Safe to call if event bus doesn't exist.
    """
    try:
        from core.events.bus import event_bus
        event_bus.on_event(handle_ecosystem_event)
        logger.info("ZugaLife ecosystem handler registered on event bus")
    except ImportError:
        logger.info("Event bus not available — ecosystem signals disabled (standalone mode)")
    except Exception:
        logger.warning("Failed to register ecosystem handler", exc_info=True)
