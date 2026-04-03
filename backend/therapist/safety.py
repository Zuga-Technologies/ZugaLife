"""Therapist safety: crisis detection, audit logging, and disclaimer logic.

CRITICAL: This module handles detection of crisis situations including
suicidal ideation, self-harm, domestic violence, eating disorders, and
child abuse. Changes to this file require careful review.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base
from core.database.session import get_session

logger = logging.getLogger(__name__)

# ── Crisis Patterns ───────────────────────────────────────────────

# Suicide & self-harm
_SUICIDE_PATTERNS = [
    r"\bsuicid\w*\b",
    r"\bkill\s+(my|him|her|them)self\b",
    r"\bwant\s+to\s+die\b",
    r"\bend\s+(my|it\s+all)\s+life\b",
    r"\bself[- ]?harm\b",
    r"\bcutting\s+(my|on)\s+(wrist|arm|leg|skin|body)\b",
    r"\boverdose\b",
    r"\bjump\s+off\b",
    r"\bhang\s+myself\b",
    r"\bnot\s+worth\s+living\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bhurt\s+(my|him|her|them)self\b",
    r"\bdon'?t\s+want\s+to\s+(be\s+)?alive\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bplanning\s+(to\s+)?(end|kill|hurt)\b",
    r"\bwish\s+i\s+was\s+dead\b",
    r"\bwish\s+i\s+was\s+never\s+born\b",
]

# Domestic violence & abuse
_ABUSE_PATTERNS = [
    r"\b(he|she|they|partner|spouse|husband|wife)\s+(hit|hits|beat|beats|choke[sd]?|strangles?)\s+me\b",
    r"\b(he|she|they)\s+(won'?t\s+let\s+me\s+leave|lock[sed]?\s+me\s+(in|out))\b",
    r"\bafraid\s+of\s+my\s+(partner|husband|wife|boyfriend|girlfriend)\b",
    r"\b(domestic|physical)\s+(violence|abuse)\b",
    r"\b(being|getting)\s+(abused|beaten|assaulted)\b",
]

# Eating disorders
_ED_PATTERNS = [
    r"\b(purging|purge|binge\s+and\s+purge)\b",
    r"\b(making\s+myself|force\s+myself\s+to)\s+(throw\s+up|vomit)\b",
    r"\bhaven'?t\s+eaten\s+in\s+\d+\s+days?\b",
    r"\bstarving\s+myself\b",
]

# Child abuse (mandatory reporting context)
_CHILD_ABUSE_PATTERNS = [
    r"\b(someone|adult)\s+(touching|molesting|abusing)\s+(a\s+)?(child|kid|minor)\b",
    r"\b(child|kid)\s+(is\s+)?being\s+(abused|hurt|beaten|molested)\b",
    r"\b(my\s+)?(parent|father|mother|uncle|teacher|coach)\s+(molest|abuse|touch)\b",
]

_ALL_PATTERNS = _SUICIDE_PATTERNS + _ABUSE_PATTERNS + _ED_PATTERNS + _CHILD_ABUSE_PATTERNS
_CRISIS_RE = re.compile("|".join(_ALL_PATTERNS), re.IGNORECASE)

# Category detection for audit logging
_CATEGORY_MAP = [
    ("suicide_self_harm", _SUICIDE_PATTERNS),
    ("domestic_violence", _ABUSE_PATTERNS),
    ("eating_disorder", _ED_PATTERNS),
    ("child_abuse", _CHILD_ABUSE_PATTERNS),
]


# ── Crisis Responses (per category) ──────────────────────────────

CRISIS_RESPONSE = (
    "I hear you, and I want you to know that what you're feeling matters. "
    "But this is beyond what I can help with — I'm an AI, and you deserve "
    "real human support right now.\n\n"
    "Please reach out:\n"
    "- **988 Suicide & Crisis Lifeline**: Call or text 988 (US)\n"
    "- **Crisis Text Line**: Text HOME to 741741\n"
    "- **International Association for Suicide Prevention**: "
    "https://www.iasp.info/resources/Crisis_Centres/\n\n"
    "You're not alone in this. These are trained people who care and can help."
)

ABUSE_RESPONSE = (
    "What you're describing sounds serious, and I want you to be safe. "
    "I'm an AI and I can't provide the help you need right now — but there are "
    "people who can.\n\n"
    "Please reach out:\n"
    "- **National Domestic Violence Hotline**: Call 1-800-799-7233 or text START to 88788\n"
    "- **Crisis Text Line**: Text HOME to 741741\n"
    "- **RAINN (sexual assault)**: Call 1-800-656-4673\n\n"
    "You deserve to be safe. These are confidential services with trained advocates."
)

ED_RESPONSE = (
    "I'm concerned about what you're describing. Eating disorders are serious "
    "medical conditions, and I'm not equipped to help with this — but professionals "
    "who specialize in this can.\n\n"
    "Please reach out:\n"
    "- **National Eating Disorders Association**: Call 1-800-931-2237 or text NEDA to 741741\n"
    "- **Crisis Text Line**: Text HOME to 741741\n\n"
    "Getting help is a sign of strength, not weakness."
)

CHILD_ABUSE_RESPONSE = (
    "What you're describing involves a child's safety, and I take that very "
    "seriously. I'm an AI and I can't intervene — but people who can need to "
    "know about this.\n\n"
    "Please contact:\n"
    "- **Childhelp National Child Abuse Hotline**: Call 1-800-422-4453\n"
    "- **Crisis Text Line**: Text HOME to 741741\n"
    "- **If a child is in immediate danger**: Call 911\n\n"
    "Reporting protects children. You're doing the right thing by paying attention."
)

_CATEGORY_RESPONSES = {
    "suicide_self_harm": CRISIS_RESPONSE,
    "domestic_violence": ABUSE_RESPONSE,
    "eating_disorder": ED_RESPONSE,
    "child_abuse": CHILD_ABUSE_RESPONSE,
}

DISCLAIMER = (
    "I'm an AI companion, not a licensed therapist. I draw from psychology, "
    "philosophy, and contemplative traditions to help you reflect. "
    "I make mistakes — please push back when something doesn't feel right."
)

PERIODIC_DISCLAIMER = (
    "\n\n---\n*Reminder: I'm an AI companion, not a therapist. "
    "If you need professional support, please reach out to a licensed provider. "
    "In crisis, call 988 or text HOME to 741741.*"
)

# ── Crisis Audit Table ────────────────────────────────────────────

class CrisisAuditLog(Base):
    """Immutable log of crisis detections. Never delete, never modify."""

    __tablename__ = "crisis_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(50))  # suicide_self_harm, domestic_violence, etc.
    matched_pattern: Mapped[str] = mapped_column(String(200))  # which pattern triggered
    response_served: Mapped[str] = mapped_column(String(50))  # which response was shown
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


# ── Detection Functions ───────────────────────────────────────────

def detect_crisis(text: str) -> bool:
    """Check if user message contains any crisis indicators."""
    return bool(_CRISIS_RE.search(text))


def detect_crisis_category(text: str) -> str | None:
    """Return the crisis category if detected, or None.

    Checks categories in priority order: suicide > child abuse > DV > ED.
    """
    for category, patterns in _CATEGORY_MAP:
        compiled = re.compile("|".join(patterns), re.IGNORECASE)
        if compiled.search(text):
            return category
    return None


def get_crisis_response(category: str | None) -> str:
    """Get the appropriate crisis response for the detected category."""
    if category and category in _CATEGORY_RESPONSES:
        return _CATEGORY_RESPONSES[category]
    return CRISIS_RESPONSE


async def log_crisis_detection(
    user_id: str,
    category: str,
    matched_text: str,
) -> None:
    """Log a crisis detection to the audit table. Fire-and-forget."""
    try:
        async with get_session() as session:
            entry = CrisisAuditLog(
                user_id=user_id,
                category=category,
                matched_pattern=matched_text[:200],
                response_served=category,
            )
            session.add(entry)
        logger.warning(
            "[CRISIS] Detected %s for user %s", category, user_id[:8]
        )
    except Exception:
        logger.exception("[CRISIS] Failed to log crisis detection")
