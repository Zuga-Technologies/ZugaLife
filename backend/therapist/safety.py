"""Therapist safety: crisis detection and disclaimer logic."""

import re

# Crisis keywords — if ANY of these appear, trigger crisis response
_CRISIS_PATTERNS = [
    r"\bsuicid\w*\b",
    r"\bkill\s+(my|him|her|them)self\b",
    r"\bwant\s+to\s+die\b",
    r"\bend\s+(my|it\s+all)\s+life\b",
    r"\bself[- ]?harm\b",
    r"\bcutting\s+(my|on)\b",
    r"\boverdose\b",
    r"\bjump\s+off\b",
    r"\bhang\s+myself\b",
    r"\bnot\s+worth\s+living\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bhurt\s+(my|him|her|them)self\b",
]

_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)

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

DISCLAIMER = (
    "I'm an AI companion, not a licensed therapist. I draw from psychology, "
    "philosophy, and contemplative traditions to help you reflect. "
    "I make mistakes — please push back when something doesn't feel right. "
    "For crisis support, call 988 or text HOME to 741741."
)


def detect_crisis(text: str) -> bool:
    """Check if user message contains crisis indicators."""
    return bool(_CRISIS_RE.search(text))
