"""ZugaLife journal CRUD + AI reflection endpoints."""

import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.journal.models"]
_schemas = sys.modules["zugalife.journal.schemas"]
_prompts = sys.modules["zugalife.journal.prompts"]

# Pull into globals for FastAPI annotation resolution
JournalEntry = _models.JournalEntry
JournalReflection = _models.JournalReflection
JournalCreateRequest = _schemas.JournalCreateRequest
JournalEntryResponse = _schemas.JournalEntryResponse
JournalEntryBrief = _schemas.JournalEntryBrief
JournalListResponse = _schemas.JournalListResponse
JournalReflectResponse = _schemas.JournalReflectResponse

# Reuse mood emoji → label mapping from prompts
_EMOJI_LABELS = _prompts._EMOJI_LABELS
MAX_REFLECTIONS = _prompts.MAX_REFLECTIONS_PER_ENTRY

router = APIRouter(prefix="/api/life/journal", tags=["life-journal"])


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    body: JournalCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new journal entry."""
    mood_label = None
    if body.mood_emoji:
        mood_label = _EMOJI_LABELS.get(body.mood_emoji)
        if not mood_label:
            raise HTTPException(status_code=422, detail="Invalid mood emoji")

    async with get_session() as session:
        entry = JournalEntry(
            user_id=user.id,
            title=body.title,
            content=body.content,
            mood_emoji=body.mood_emoji,
            mood_label=mood_label,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        return JournalEntryResponse.model_validate(entry)


@router.get("", response_model=JournalListResponse)
async def list_journal_entries(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    """List journal entries with pagination. Returns brief previews."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_session() as session:
        # Get total count
        count_result = await session.execute(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.user_id == user.id,
                JournalEntry.created_at >= since,
            )
        )
        total = count_result.scalar_one()

        # Get entries
        result = await session.execute(
            select(JournalEntry)
            .where(
                JournalEntry.user_id == user.id,
                JournalEntry.created_at >= since,
            )
            .order_by(desc(JournalEntry.created_at))
            .offset(offset)
            .limit(limit)
        )
        entries = result.scalars().all()

        briefs = [
            JournalEntryBrief(
                id=e.id,
                title=e.title,
                content_preview=e.content[:200],
                mood_emoji=e.mood_emoji,
                mood_label=e.mood_label,
                reflection_count=len(e.reflections),
                created_at=e.created_at,
            )
            for e in entries
        ]

    return JournalListResponse(entries=briefs, total=total)


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Get a single journal entry with all reflections."""
    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        return JournalEntryResponse.model_validate(entry)


@router.post(
    "/{entry_id}/reflect",
    response_model=JournalReflectResponse,
)
async def reflect_on_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate an AI reflection on a journal entry. Costs credits."""
    try:
        from core.ai.gateway import BudgetExhaustedError, PromptBlockedError, ai_call
    except ImportError:
        raise HTTPException(
            status_code=503, detail="AI reflections not available in standalone mode",
        )

    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        if len(entry.reflections) >= MAX_REFLECTIONS:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {MAX_REFLECTIONS} reflections per entry",
            )

        # Build prompt with anti-repetition context
        previous = [r.content for r in entry.reflections]
        prompt = _prompts.build_reflection_prompt(
            journal_content=entry.content,
            title=entry.title,
            mood_emoji=entry.mood_emoji,
            previous_reflections=previous if previous else None,
        )

        # AI call — task="chat" routes to Kimi K2.5 (cheapest)
        try:
            ai_response = await ai_call(prompt, task="chat", max_tokens=2048)
        except BudgetExhaustedError:
            raise HTTPException(
                status_code=402, detail="Daily AI budget exhausted",
            )
        except PromptBlockedError:
            raise HTTPException(
                status_code=400, detail="Content blocked by security filter",
            )

        reflection = JournalReflection(
            journal_entry_id=entry.id,
            content=ai_response.content,
            model_used=ai_response.model,
            cost=ai_response.cost,
        )
        session.add(reflection)
        await session.flush()
        await session.refresh(reflection)

        new_total = len(entry.reflections) + 1  # +1 for the one just created
        remaining = MAX_REFLECTIONS - new_total

        return JournalReflectResponse(
            reflection=_schemas.JournalReflectionResponse.model_validate(
                reflection,
            ),
            remaining=remaining,
        )


@router.delete("/{entry_id}", status_code=204)
async def delete_journal_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a journal entry and all its reflections (cascade)."""
    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        await session.delete(entry)
