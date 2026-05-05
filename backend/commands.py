"""ZugaLife — ZugaOS command catalog.

This studio's authoritative list of intents that ZugaOS can dispatch.
Bump version on breaking changes; the aggregator caches by (studio, version).

Phase 2 = static catalog. When ZugaLife grows dynamic capabilities (e.g. user-
specific habit set), this can become a function that builds the list at request
time — same shape, just no longer constant.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/life", tags=["life-zugaos"])

CATALOG = {
    "studio": "life",
    "version": "1.0.0",
    "commands": [
        {
            "intent": "life.summary_today",
            "description": "Summarize the user's wellness state for today: sleep, mood, completed habits, journal sentiment.",
            "args_schema": {},
            "requires_auth": True,
            "estimated_cost_tokens": 0.0,
        },
        {
            "intent": "life.recent_journal",
            "description": "Return the user's most recent N journal entries with timestamps and sentiment.",
            "args_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}},
            },
            "requires_auth": True,
            "estimated_cost_tokens": 0.0,
        },
        {
            "intent": "life.habit_check",
            "description": "Report whether the user has completed today's habits, with streak counts.",
            "args_schema": {},
            "requires_auth": True,
            "estimated_cost_tokens": 0.0,
        },
        {
            "intent": "life.log_mood",
            "description": "Log a mood entry for the user with an optional note.",
            "args_schema": {
                "type": "object",
                "properties": {
                    "mood": {"type": "string", "enum": ["great", "good", "okay", "low", "rough"]},
                    "note": {"type": "string", "maxLength": 500},
                },
                "required": ["mood"],
            },
            "requires_auth": True,
            "estimated_cost_tokens": 0.5,
        },
    ],
}


@router.get("/commands")
async def get_commands() -> dict:
    """Return ZugaLife's intent catalog. Public — capability descriptors only,
    no user data. ZugaOS aggregator merges this with other studios' catalogs."""
    return CATALOG
