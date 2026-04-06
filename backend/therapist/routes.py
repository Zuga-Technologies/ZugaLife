"""ZugaLife therapist endpoints.

SECURITY: All AI calls use task="therapist" which routes ONLY to Venice.
Therapist session notes are never queried by other ZugaLife modules.
"""

import logging
import re
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

logger = logging.getLogger(__name__)

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.therapist.models"]
_schemas = sys.modules["zugalife.therapist.schemas"]
_prompts = sys.modules["zugalife.therapist.prompts"]
_safety = sys.modules["zugalife.therapist.safety"]
_context = sys.modules["zugalife.therapist.context"]

def _get_gam_engine():
    """Lazy lookup — gamification loads after therapist in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

TherapistSessionNote = _models.TherapistSessionNote

TherapistChatRequest = _schemas.TherapistChatRequest
TherapistChatResponse = _schemas.TherapistChatResponse
TherapistEndSessionRequest = _schemas.TherapistEndSessionRequest
SessionNoteResponse = _schemas.SessionNoteResponse
SessionNoteListResponse = _schemas.SessionNoteListResponse
SessionNoteUpdateRequest = _schemas.SessionNoteUpdateRequest
TherapistStatusResponse = _schemas.TherapistStatusResponse
ConversationStarter = _schemas.ConversationStarter
TherapistStartersResponse = _schemas.TherapistStartersResponse

SYSTEM_PROMPT = _prompts.SYSTEM_PROMPT
FIRST_SESSION_GREETING = _prompts.FIRST_SESSION_GREETING
RETURNING_SESSION_GREETING = _prompts.RETURNING_SESSION_GREETING
GREETING_GENERATION_PROMPT = _prompts.GREETING_GENERATION_PROMPT
SESSION_WINDING_DOWN = _prompts.SESSION_WINDING_DOWN
SESSION_SUMMARY_PROMPT = _prompts.SESSION_SUMMARY_PROMPT

MAX_SESSIONS_PER_DAY = 5
MAX_MESSAGES_PER_SESSION = 20

router = APIRouter(prefix="/api/life/therapist", tags=["life-therapist"])


# --- Status ---


@router.get("/status", response_model=TherapistStatusResponse)
async def therapist_status(
    user: CurrentUser = Depends(get_current_user),
):
    """Get therapist availability: sessions used/remaining, first session flag."""
    used = await _context.count_today_sessions(user.id)
    first = await _context.is_first_session(user.id)

    return TherapistStatusResponse(
        sessions_used=used,
        sessions_limit=MAX_SESSIONS_PER_DAY,
        sessions_remaining=max(0, MAX_SESSIONS_PER_DAY - used),
        is_first_session=first,
    )


# --- Greeting ---


@router.get("/greeting")
async def therapist_greeting(
    user: CurrentUser = Depends(get_current_user),
):
    """Get a context-aware greeting for starting a new session."""
    from core.ai.gateway import BudgetExhaustedError, CreditBlockedError

    first = await _context.is_first_session(user.id)
    context_summary = await _context.build_user_context(user.id)

    try:
        if first:
            greeting = FIRST_SESSION_GREETING
        else:
            # Generate a natural greeting via Venice instead of dumping raw data
            greeting = await _generate_returning_greeting(user.id, user.email, context_summary)
    except (CreditBlockedError, BudgetExhaustedError):
        raise HTTPException(status_code=402, detail="You're out of tokens. Add more to continue using the Wellness Bot.")

    return {
        "greeting": greeting,
        "is_first_session": first,
        "disclaimer": _safety.DISCLAIMER,
    }


# --- Conversation Starters ---


@router.get("/starters", response_model=TherapistStartersResponse)
async def conversation_starters(
    user: CurrentUser = Depends(get_current_user),
):
    """Generate suggested conversation starters based on recent user data."""
    starters = []

    async with get_session() as session:
        # Check recent mood trends
        try:
            MoodEntry = sys.modules["zugalife.models"].MoodEntry
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(days=3)
            result = await session.execute(
                select(MoodEntry.label, MoodEntry.emoji)
                .where(MoodEntry.user_id == user.id, MoodEntry.created_at >= since)
                .order_by(desc(MoodEntry.created_at))
                .limit(5)
            )
            recent_moods = result.all()
            if recent_moods:
                neg_moods = [m for m in recent_moods if m.label in ("Sad", "Anxious", "Angry", "Frustrated", "Tired")]
                if len(neg_moods) >= 2:
                    labels = ", ".join(set(m.label.lower() for m in neg_moods[:3]))
                    starters.append(ConversationStarter(
                        text=f"I've been feeling {labels} lately — can we talk about that?",
                        source="mood",
                    ))
                elif recent_moods:
                    starters.append(ConversationStarter(
                        text=f"My mood has been mostly {recent_moods[0].label.lower()} — what does that tell you?",
                        source="mood",
                    ))
        except Exception:
            pass

        # Check habit performance
        try:
            HabitDef = sys.modules["zugalife.habits.models"].HabitDefinition
            HabitLog = sys.modules["zugalife.habits.models"].HabitLog
            from datetime import date, timedelta
            week_ago = date.today() - timedelta(days=6)
            habits = await session.execute(
                select(HabitDef.name)
                .where(HabitDef.user_id == user.id, HabitDef.is_active == True)
            )
            active_habits = habits.scalars().all()
            logs = await session.execute(
                select(func.count())
                .select_from(HabitLog)
                .where(HabitLog.user_id == user.id, HabitLog.log_date >= week_ago, HabitLog.completed == True)
            )
            log_count = logs.scalar() or 0
            if active_habits and log_count < len(active_habits) * 3:
                starters.append(ConversationStarter(
                    text="I've been struggling to keep up with my habits — can you help me figure out why?",
                    source="habit",
                ))
        except Exception:
            pass

        # Check recent journal entries
        try:
            JournalEntry = sys.modules["zugalife.journal.models"].JournalEntry
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(days=7)
            result = await session.execute(
                select(JournalEntry.title, JournalEntry.mood_label)
                .where(JournalEntry.user_id == user.id, JournalEntry.created_at >= since)
                .order_by(desc(JournalEntry.created_at))
                .limit(3)
            )
            entries = result.all()
            if entries and entries[0].title:
                starters.append(ConversationStarter(
                    text=f"I wrote about \"{entries[0].title}\" recently — can we dig into that?",
                    source="journal",
                ))
        except Exception:
            pass

    # Always include general starters
    general_starters = [
        "Something's been on my mind and I need to talk it through.",
        "I'm feeling stuck and I'm not sure why.",
        "Things are actually going well — I want to understand why so I can keep it up.",
    ]
    for gs in general_starters[:2]:
        if len(starters) < 5:
            starters.append(ConversationStarter(text=gs, source="general"))

    return TherapistStartersResponse(starters=starters[:5])


# --- Chat ---


@router.post("/chat", response_model=TherapistChatResponse)
async def therapist_chat(
    body: TherapistChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Send a message to the therapist and get a response.

    The frontend maintains the full conversation in memory and sends
    the growing message array with each request. Nothing is stored
    server-side until end-session.
    """
    # Rate limit: sessions per day
    used = await _context.count_today_sessions(user.id)
    if used >= MAX_SESSIONS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily session limit reached ({MAX_SESSIONS_PER_DAY}/day). Try again tomorrow.",
        )

    # Message limit per session
    message_count = len(body.messages)
    if message_count > MAX_MESSAGES_PER_SESSION * 2:  # user + assistant messages
        raise HTTPException(
            status_code=400,
            detail=f"Session message limit reached ({MAX_MESSAGES_PER_SESSION} exchanges). "
            "Please end this session to save your notes.",
        )

    # Crisis detection on last 5 user messages (not just the latest)
    recent_user_msgs = [
        m.content for m in body.messages[-10:]
        if m.role == "user"
    ][-5:]
    for msg_text in recent_user_msgs:
        category = _safety.detect_crisis_category(msg_text)
        if category:
            # Log to audit table (fire-and-forget)
            await _safety.log_crisis_detection(
                user_id=user.id,
                category=category,
                matched_text=msg_text[:200],
            )
            response_text = _safety.get_crisis_response(category)
            return TherapistChatResponse(
                content=response_text,
                message_index=message_count,
                session_messages_remaining=MAX_MESSAGES_PER_SESSION - (message_count // 2),
                cost=0.0,
                crisis_detected=True,
            )

    # Build context-enriched system prompt
    first_session = await _context.is_first_session(user.id)
    context_summary = await _context.build_user_context(user.id)
    system_prompt = SYSTEM_PROMPT + "\n\n## Current User Context\n\n"
    if first_session:
        system_prompt += (
            "This is the user's FIRST session. They are just getting started with ZugaLife. "
            "Don't over-analyze empty or sparse data — treat them as someone exploring, "
            "not someone who fell off track.\n\n"
        )
    system_prompt += context_summary

    # When nearing session end, hint the AI to wrap up naturally
    user_exchanges = (message_count + 1) // 2
    remaining = MAX_MESSAGES_PER_SESSION - user_exchanges
    if remaining <= 3:
        system_prompt += SESSION_WINDING_DOWN

    # Assemble messages: system + conversation history
    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m.role, "content": m.content} for m in body.messages],
    ]

    # Call Venice via gateway (task="therapist" enforces Venice-only routing)
    from core.ai.gateway import BudgetExhaustedError, CreditBlockedError, PromptBlockedError, ai_call

    try:
        response = await ai_call(
            prompt="",  # unused when messages is provided
            task="therapist",
            max_tokens=4096,
            messages=messages,
            user_id=user.id,
            user_email=user.email,
        )
    except (BudgetExhaustedError, CreditBlockedError):
        raise HTTPException(status_code=402, detail="You're out of tokens. Add more to continue using the Wellness Bot.")
    except PromptBlockedError:
        raise HTTPException(status_code=400, detail="Content blocked by security filter")
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Wellness Bot is temporarily unavailable")
    except Exception:
        logger.exception("Venice API call failed")
        raise HTTPException(status_code=503, detail="Wellness Bot is temporarily unavailable. Please try later.")

    # If Venice returned empty (model spent all tokens reasoning), retry once
    if not response.content.strip():
        logger.warning("Venice returned empty chat response, retrying")
        try:
            response = await ai_call(
                prompt="",
                task="therapist",
                max_tokens=4096,
                messages=messages,
                user_id=user.id,
                user_email=user.email,
            )
        except Exception:
            pass

    content = response.content.strip()
    if not content:
        content = "I'm sorry, I lost my train of thought. Could you repeat what you just said?"

    # Periodic disclaimer every 10 exchanges
    user_exchanges = (message_count + 1) // 2
    if user_exchanges > 0 and user_exchanges % 10 == 0:
        content += _safety.PERIODIC_DISCLAIMER

    # End-of-session reflection prompt (when 2 exchanges left)
    if user_exchanges == MAX_MESSAGES_PER_SESSION - 2:
        content += ("\n\nBefore we wrap up — what's one thing from this conversation "
                    "that you want to sit with or try before next time?")

    return TherapistChatResponse(
        content=content,
        message_index=message_count + 1,
        session_messages_remaining=max(0, MAX_MESSAGES_PER_SESSION - user_exchanges),
        cost=response.cost,
    )


# --- End Session (generate + store notes) ---


@router.post("/end-session", response_model=SessionNoteResponse, status_code=201)
async def end_session(
    body: TherapistEndSessionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """End a therapy session: generate a summary note from the conversation.

    The full conversation is sent one final time for summarization,
    then the client discards it. Only the structured note persists.
    """
    # Format conversation for summary prompt
    conversation_text = _format_conversation(body.messages)

    summary_prompt = SESSION_SUMMARY_PROMPT.format(conversation=conversation_text)
    messages = [
        {"role": "system", "content": "You are a clinical note-taker. Summarize therapy sessions accurately."},
        {"role": "user", "content": summary_prompt},
    ]

    from core.ai.gateway import BudgetExhaustedError, CreditBlockedError, ai_call

    try:
        response = await ai_call(
            prompt="",
            task="therapist",
            max_tokens=4096,
            messages=messages,
            user_id=user.id,
            user_email=user.email,
        )
        # Retry once if Venice returned empty (reasoning-only response)
        if not response.content.strip():
            logger.warning("Empty session summary, retrying")
            response = await ai_call(
                prompt="",
                task="therapist",
                max_tokens=4096,
                messages=messages,
                user_id=user.id,
                user_email=user.email,
            )
    except (CreditBlockedError, BudgetExhaustedError):
        logger.warning("Insufficient tokens for session summary: user=%s", user.id)
        response = None
        summary_handled = True
        themes = "Session completed (summary skipped — not enough tokens)"
        patterns = None
        follow_up = None
        mood = None
        total_cost = 0.0
    except Exception:
        logger.exception("Failed to generate session summary")
        response = None
        summary_handled = False
    else:
        summary_handled = False

    # Parse the structured summary (skip if already handled by credit error)
    if summary_handled:
        pass  # themes etc. already set above
    elif response and response.content.strip():
        themes, patterns, follow_up, mood = _parse_summary(response.content)
        total_cost = response.cost
    else:
        themes = "Session completed (no summary generated)"
        patterns = None
        follow_up = None
        mood = None
        total_cost = response.cost if response else 0.0

    # Save session note
    async with get_session() as session:
        note = TherapistSessionNote(
            user_id=user.id,
            themes=themes,
            patterns=patterns,
            follow_up=follow_up,
            mood_snapshot=mood,
            mood_before=body.mood_before,
            mood_after=body.mood_after,
            rating=body.rating,
            message_count=len(body.messages),
            cost=total_cost,
            provider="venice",
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)

        gam = _get_gam_engine()
        if gam:
            try:
                await gam.award_xp(
                    session, user_id=user.id,
                    source="therapist_session",
                    description=f"Therapist session ({len(body.messages)} messages)",
                )
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

    logger.info(
        "Therapist session saved: user=%s messages=%d cost=$%.4f",
        user.id, len(body.messages), total_cost,
    )

    return SessionNoteResponse.model_validate(note)


# --- Session Notes CRUD ---


@router.get("/notes", response_model=SessionNoteListResponse)
async def list_notes(
    user: CurrentUser = Depends(get_current_user),
):
    """List all therapist session notes for the user, newest first."""
    async with get_session() as session:
        result = await session.execute(
            select(TherapistSessionNote)
            .where(TherapistSessionNote.user_id == user.id)
            .order_by(desc(TherapistSessionNote.created_at))
        )
        notes = result.scalars().all()

    return SessionNoteListResponse(
        notes=[SessionNoteResponse.model_validate(n) for n in notes],
        total=len(notes),
    )


@router.get("/notes/{note_id}", response_model=SessionNoteResponse)
async def get_note(
    note_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Get a single session note."""
    async with get_session() as session:
        note = await _get_user_note(session, note_id, user.id)
    return SessionNoteResponse.model_validate(note)


@router.patch("/notes/{note_id}", response_model=SessionNoteResponse)
async def update_note(
    note_id: int,
    body: SessionNoteUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update a session note (user can edit themes, patterns, follow-up)."""
    async with get_session() as session:
        note = await _get_user_note(session, note_id, user.id)

        if "themes" in body.model_fields_set and body.themes is not None:
            note.themes = body.themes
        if "patterns" in body.model_fields_set:
            note.patterns = body.patterns
        if "follow_up" in body.model_fields_set:
            note.follow_up = body.follow_up

        await session.flush()
        await session.refresh(note)

    return SessionNoteResponse.model_validate(note)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a session note."""
    async with get_session() as session:
        note = await _get_user_note(session, note_id, user.id)
        await session.delete(note)


# --- Private helpers ---


async def _get_user_note(session, note_id: int, user_id: str) -> TherapistSessionNote:
    """Fetch a session note ensuring it belongs to the user."""
    result = await session.execute(
        select(TherapistSessionNote).where(TherapistSessionNote.id == note_id)
    )
    note = result.scalar_one_or_none()
    if not note or note.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session note not found")
    return note


async def _generate_returning_greeting(user_id: str, user_email: str, context_summary: str) -> str:
    """Generate a warm, natural returning-user greeting via Venice.

    Falls back to the static template if Venice is unavailable.
    Raises CreditBlockedError/BudgetExhaustedError if user has no tokens.
    """
    last_ref = await _context.get_last_session_reference(user_id)
    last_note = f"Last session: {last_ref}" if last_ref else ""

    user_prompt = GREETING_GENERATION_PROMPT.format(
        context_summary=context_summary or "No data available yet.",
        last_session_note=last_note,
    )

    from core.ai.gateway import BudgetExhaustedError, CreditBlockedError, ai_call

    try:
        response = await ai_call(
            prompt="",
            task="therapist",
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            user_id=user_id,
            user_email=user_email,
        )
        greeting = response.content.strip()
        if not greeting:
            logger.warning("Venice returned empty greeting (reasoning-only), using fallback")
            return RETURNING_SESSION_GREETING.format(
                last_session_reference=last_ref or "It's good to see you again.",
            )
        return greeting
    except (CreditBlockedError, BudgetExhaustedError):
        raise  # Let token errors propagate to the endpoint
    except Exception:
        logger.warning("Failed to generate greeting via Venice, using static fallback")
        return RETURNING_SESSION_GREETING.format(
            last_session_reference=last_ref or "It's good to see you again.",
        )


def _format_conversation(messages) -> str:
    """Format a messages array into readable text for the summary prompt."""
    lines = []
    for msg in messages:
        role = (msg.role if hasattr(msg, "role") else msg.get("role", "unknown")).capitalize()
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _parse_summary(text: str) -> tuple[str, str | None, str | None, str | None]:
    """Parse the structured session summary from AI response.

    Expected format:
        THEMES:\n...\nPATTERNS:\n...\nFOLLOW-UP:\n...\nMOOD:\n...
    """
    themes = _extract_section(text, "THEMES")
    patterns = _extract_section(text, "PATTERNS")
    follow_up = _extract_section(text, "FOLLOW-UP")
    mood = _extract_section(text, "MOOD")

    # Fallback: if parsing fails, use the whole text as themes
    if not themes:
        cleaned = text.strip()
        themes = cleaned[:2000] if cleaned else "Session completed (no summary generated)"

    return themes, patterns, follow_up, mood


def _extract_section(text: str, header: str) -> str | None:
    """Extract content between a header and the next header."""
    # Try strict format first (header on its own line)
    pattern = rf"{header}\s*:\s*\n(.*?)(?=\n[A-Z-]+\s*:|$)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        # Fallback: content on same line as header
        pattern = rf"{header}\s*:\s*(.*?)(?=\n[A-Z-]+\s*:|$)"
        match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None
    content = match.group(1).strip()
    if not content or content.lower() in ("none", "none identified", "no specific follow-up"):
        return None
    return content
