"""Lightweight sentiment classification for wellness companion expressions.

Drives the avatar's emotional state (visor color, posture, idle tempo)
from the assistant's reply text. Keyword + emoji buckets — no LLM call,
no per-message cost. Mood labels match the VRM 1.0 expression presets so
human-VRM characters can reuse the same labels via blendshapes later.
"""

import re
from typing import Literal

Mood = Literal["happy", "sad", "angry", "surprised", "relaxed", "neutral"]

# Word stems chosen for assistant replies (validation/reflection language),
# not user venting. Stems use \b word boundaries so "saddle" doesn't trip "sad".
_PATTERNS: dict[Mood, list[str]] = {
    "happy": [
        r"\b(wonderful|great|love that|proud of you|beautiful|celebrate|joy|delight)\b",
        r"\b(that's amazing|so glad|happy to hear|good for you|well done)\b",
        r"[\U0001F600-\U0001F60F\U0001F970✨\U0001F389]",
    ],
    "sad": [
        r"\b(i hear you|that sounds (hard|painful|heavy|exhausting|lonely))\b",
        r"\b(grief|loss|hurts|painful|heartbreaking|sorry you're)\b",
        r"\b(makes sense (you|that you|to))\b.*\b(hurt|tired|drained|sad|down)\b",
    ],
    "angry": [
        r"\b(that's not (okay|right|fair)|you didn't deserve|crossed a line)\b",
        r"\b(boundary|violated|unacceptable)\b",
    ],
    "surprised": [
        r"\b(wait|really\?|oh\b|that's a lot|hadn't considered|interesting that)\b",
        r"[⁉‼\U0001F62E\U0001F632]",
    ],
    "relaxed": [
        r"\b(take a breath|gently|notice|let's slow down|one thing at a time)\b",
        r"\b(it's okay to|you don't have to|rest|softer|kind to yourself)\b",
    ],
}

_COMPILED: dict[Mood, list[re.Pattern]] = {
    mood: [re.compile(p, re.IGNORECASE) for p in pats]
    for mood, pats in _PATTERNS.items()
}

# Priority when multiple buckets match. Sad/angry beat happy because validation
# language often co-occurs with reflective warmth ("I hear you — that's beautiful
# you held that").
_PRIORITY: list[Mood] = ["angry", "sad", "surprised", "relaxed", "happy"]


def classify(text: str) -> tuple[Mood, float]:
    """Return (mood, intensity 0..1) for an assistant reply.

    Intensity is hit-count normalized — 1 match = 0.4, 3+ matches = 1.0.
    Default (no matches) is ('neutral', 0.0).
    """
    if not text or not text.strip():
        return "neutral", 0.0

    hits: dict[Mood, int] = {}
    for mood in _PRIORITY:
        n = sum(1 for r in _COMPILED[mood] if r.search(text))
        if n:
            hits[mood] = n

    if not hits:
        return "neutral", 0.0

    winner = next(m for m in _PRIORITY if m in hits)
    n = hits[winner]
    intensity = min(1.0, 0.4 + 0.3 * (n - 1))
    return winner, intensity
