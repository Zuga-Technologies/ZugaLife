"""ZugaLife meditation endpoints."""

import logging
import struct
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.meditation.models"]
_schemas = sys.modules["zugalife.meditation.schemas"]
_prompts = sys.modules["zugalife.meditation.prompts"]

# Pull into globals for FastAPI annotation resolution
MeditationSession = _models.MeditationSession

GenerateRequest = _schemas.GenerateRequest
MoodAfterRequest = _schemas.MoodAfterRequest
SessionResponse = _schemas.SessionResponse
SessionBrief = _schemas.SessionBrief
SessionListResponse = _schemas.SessionListResponse
RemainingResponse = _schemas.RemainingResponse

DAILY_LIMIT = _prompts.DAILY_SESSION_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/life/meditation", tags=["life-meditation"])

# Audio storage directory (relative to backend working dir)
_AUDIO_DIR = Path("data/meditation_audio")

# Resolve symlinks once at import time.
# On Railway, _AUDIO_DIR is a symlink to /data/meditation_audio (persistent volume).
# The volume may not have this subdir yet.  resolve() dereferences the symlink so
# all subsequent mkdir / path operations use the real path, avoiding the
# "FileExistsError: symlink already exists" trap in pathlib.mkdir(parents=True).
_AUDIO_DIR = _AUDIO_DIR.resolve()
_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# --- Generate ---


@router.post("/generate", response_model=SessionResponse, status_code=201)
async def generate_meditation(
    body: GenerateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate a new AI meditation session with audio."""
    # Check daily limit
    used = await _sessions_today(user.id)
    if used >= DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've used all {DAILY_LIMIT} meditation sessions today. Come back tomorrow.",
        )

    # Import AI dependencies (fails gracefully in standalone mode)
    try:
        from core.ai.gateway import BudgetExhaustedError, PromptBlockedError, ai_call
        from core.ai.providers import call_openai_tts
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Meditation generation not available in standalone mode",
        )

    # Gather personalization context
    mood_ctx = await _gather_mood_context(user.id)
    habit_ctx = await _gather_habit_context(user.id)
    journal_ctx = await _gather_journal_context(user.id)
    prev_titles = await _get_previous_titles(user.id)

    # 1. Generate meditation script via LLM — single pass, no retry
    prompt = _prompts.build_meditation_prompt(
        meditation_type=body.type.value,
        length=body.length.value,
        focus=body.focus,
        mood_context=mood_ctx,
        habit_context=habit_ctx,
        journal_context=journal_ctx,
        previous_titles=prev_titles,
    )

    max_tokens = 8192 if body.length.value == "long" else 4096
    total_cost = 0.0

    from core.ai.gateway import CreditBlockedError
    try:
        script_response = await ai_call(
            prompt, task="creative", max_tokens=max_tokens,
            user_id=user.id, user_email=user.email,
        )
        total_cost += script_response.cost
    except (BudgetExhaustedError, CreditBlockedError):
        raise HTTPException(status_code=402, detail="Daily AI budget exhausted")
    except PromptBlockedError:
        raise HTTPException(status_code=400, detail="Content blocked by security filter")

    raw_script = script_response.content.strip()
    title, transcript = _parse_script(raw_script)

    # 2. Convert script to audio via TTS
    tts_text = _prepare_tts_text(transcript)
    try:
        tts_result = await call_openai_tts(
            text=tts_text,
            voice=body.voice.value,
            speed=0.9,
        )
    except Exception as e:
        logger.error("TTS generation failed: %s", e)
        raise HTTPException(status_code=502, detail="Audio generation failed")

    total_cost += tts_result.cost

    # Measure actual audio duration from MP3 frame headers
    actual_seconds = int(_mp3_duration_seconds(tts_result.audio_bytes))
    logger.info(
        "Meditation generated: length=%s, words=%d, audio=%ds (%s), title=%r",
        body.length.value, len(transcript.split()), actual_seconds,
        f"{actual_seconds // 60}:{actual_seconds % 60:02d}", title,
    )

    # 3. Save audio file
    import time
    user_dir = _AUDIO_DIR / user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    temp_filename = f"{int(time.time())}_{body.type.value}.mp3"
    audio_path = user_dir / temp_filename
    audio_path.write_bytes(tts_result.audio_bytes)

    # 4. Save session to database
    async with get_session() as session:
        meditation = MeditationSession(
            user_id=user.id,
            type=body.type.value,
            length=body.length.value,
            duration_seconds=actual_seconds,
            ambience=body.ambience.value,
            voice=body.voice.value,
            focus=body.focus,
            title=title,
            transcript=transcript,
            audio_filename=f"{user.id}/{temp_filename}",
            model_used=script_response.model,
            tts_model=tts_result.model,
            cost=total_cost,
        )
        session.add(meditation)
        await session.flush()
        await session.refresh(meditation)

    logger.info(
        "Meditation saved: user=%s type=%s length=%s duration=%ds cost=$%.4f",
        user.id, body.type.value, body.length.value, actual_seconds, total_cost,
    )

    return SessionResponse.model_validate(meditation)


# --- CRUD ---


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: CurrentUser = Depends(get_current_user),
):
    """List past meditation sessions (most recent first)."""
    async with get_session() as session:
        count_result = await session.execute(
            select(func.count())
            .select_from(MeditationSession)
            .where(MeditationSession.user_id == user.id)
        )
        total = count_result.scalar_one()

        result = await session.execute(
            select(MeditationSession)
            .where(MeditationSession.user_id == user.id)
            .order_by(desc(MeditationSession.created_at))
            .limit(50)
        )
        sessions = result.scalars().all()

    return SessionListResponse(
        sessions=[SessionBrief.model_validate(s) for s in sessions],
        total=total,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_detail(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Get full session detail including transcript and audio URL."""
    async with get_session() as db:
        meditation = await _get_user_session(db, session_id, user.id)
    return SessionResponse.model_validate(meditation)


@router.patch("/sessions/{session_id}/favorite", response_model=SessionResponse)
async def toggle_favorite(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Toggle a session's favorite status."""
    async with get_session() as db:
        meditation = await _get_user_session(db, session_id, user.id)
        meditation.is_favorite = not meditation.is_favorite
        await db.flush()
        await db.refresh(meditation)
    return SessionResponse.model_validate(meditation)


@router.patch("/sessions/{session_id}/mood", response_model=SessionResponse)
async def set_mood_after(
    session_id: int,
    body: MoodAfterRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Set the post-session mood emoji."""
    async with get_session() as db:
        meditation = await _get_user_session(db, session_id, user.id)
        meditation.mood_after = body.emoji
        await db.flush()
        await db.refresh(meditation)
    return SessionResponse.model_validate(meditation)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a meditation session and its audio file."""
    async with get_session() as db:
        meditation = await _get_user_session(db, session_id, user.id)

        # Delete audio file
        audio_path = _AUDIO_DIR / meditation.audio_filename
        if audio_path.exists():
            audio_path.unlink()

        await db.delete(meditation)


# --- Audio serving ---


@router.get("/audio/{user_id}/{filename}")
async def serve_audio(
    user_id: str,
    filename: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Serve a meditation audio file. Users can only access their own files."""
    if user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    audio_path = _AUDIO_DIR / user_id / filename
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=filename,
    )


# --- Remaining count ---


@router.get("/remaining", response_model=RemainingResponse)
async def get_remaining(
    user: CurrentUser = Depends(get_current_user),
):
    """Get how many meditation sessions remain today."""
    used = await _sessions_today(user.id)
    return RemainingResponse(
        used=used,
        limit=DAILY_LIMIT,
        remaining=max(0, DAILY_LIMIT - used),
    )


# --- Private helpers ---


async def _get_user_session(db, session_id: int, user_id: str) -> MeditationSession:
    """Fetch a session ensuring it belongs to the user."""
    result = await db.execute(
        select(MeditationSession).where(MeditationSession.id == session_id)
    )
    meditation = result.scalar_one_or_none()
    if not meditation or meditation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return meditation


async def _sessions_today(user_id: str) -> int:
    """Count how many sessions a user has generated today."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    async with get_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(MeditationSession)
            .where(
                MeditationSession.user_id == user_id,
                MeditationSession.created_at >= today_start,
            )
        )
        return result.scalar_one()


def _parse_script(raw: str) -> tuple[str, str]:
    """Parse AI output: first line = title, rest = transcript."""
    import re

    lines = raw.strip().split("\n")
    title = lines[0].strip()
    # Strip common LLM formatting: markdown headers, bold, quotes, "Title:" prefix
    title = re.sub(r"^#+\s*", "", title)        # ## Title → Title
    title = re.sub(r"^\*+\s*|\s*\*+$", "", title)  # **Title** → Title
    title = re.sub(r'^["\']|["\']$', "", title)  # "Title" → Title
    title = re.sub(r"^Title:\s*", "", title, flags=re.IGNORECASE)  # Title: X → X
    title = title.strip()

    # Skip blank lines between title and body
    body_start = 1
    for i in range(1, len(lines)):
        if lines[i].strip():
            body_start = i
            break
    transcript = "\n".join(lines[body_start:]).strip()
    return title[:200], transcript


def _mp3_duration_seconds(data: bytes) -> float:
    """Calculate MP3 audio duration in seconds by parsing frame headers.

    Walks the MP3 byte stream, decoding each frame header to extract the
    sample rate and samples-per-frame.  Works with both MPEG1 and MPEG2
    Layer III (the formats OpenAI TTS produces).  No external dependencies.
    """
    # MPEG1 Layer III bitrate table (kbps, index 0 and 15 are invalid)
    _BR_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    # MPEG2/2.5 Layer III bitrate table
    _BR_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    _SR_V1 = [44100, 48000, 32000, 0]
    _SR_V2 = [22050, 24000, 16000, 0]
    _SR_V25 = [11025, 12000, 8000, 0]

    total_seconds = 0.0
    pos = 0
    end = len(data) - 4

    while pos < end:
        # Sync word: 11 set bits (0xFFE0)
        if data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
            pos += 1
            continue

        header = struct.unpack(">I", data[pos : pos + 4])[0]
        version = (header >> 19) & 3   # 3=V1, 2=V2, 0=V2.5
        layer = (header >> 17) & 3     # 1=Layer III
        br_idx = (header >> 12) & 0xF
        sr_idx = (header >> 10) & 3
        padding = (header >> 9) & 1

        if layer != 1:  # only Layer III
            pos += 1
            continue

        if version == 3:  # MPEG1
            bitrate = _BR_V1[br_idx] * 1000
            samplerate = _SR_V1[sr_idx]
            samples = 1152
            frame_len = (144 * bitrate) // samplerate + padding if bitrate and samplerate else 0
        elif version == 2:  # MPEG2
            bitrate = _BR_V2[br_idx] * 1000
            samplerate = _SR_V2[sr_idx]
            samples = 576
            frame_len = (72 * bitrate) // samplerate + padding if bitrate and samplerate else 0
        elif version == 0:  # MPEG2.5
            bitrate = _BR_V2[br_idx] * 1000
            samplerate = _SR_V25[sr_idx]
            samples = 576
            frame_len = (72 * bitrate) // samplerate + padding if bitrate and samplerate else 0
        else:
            pos += 1
            continue

        if frame_len < 1 or samplerate < 1:
            pos += 1
            continue

        total_seconds += samples / samplerate
        pos += frame_len

    return total_seconds


def _prepare_tts_text(transcript: str) -> str:
    """Replace pause markers and fix formatting for natural TTS pacing.

    OpenAI TTS doesn't support SSML, but it respects punctuation and
    line breaks for pacing. We use heavy punctuation to create real
    silences — multiple paragraph breaks produce noticeable gaps.
    Also converts bare digits to words for proper TTS pronunciation.
    """
    import re

    # Convert bare digits to words (e.g. "1" -> "one")
    _DIGIT_WORDS = {
        "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
        "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
    }
    text = transcript
    for digit, word in _DIGIT_WORDS.items():
        # Match digit surrounded by word boundaries (not inside larger numbers)
        text = re.sub(rf"\b{digit}\b", word, text)

    # [PAUSE 5s] -> heavy pause (triple ellipsis with double paragraph break)
    text = re.sub(r"\[PAUSE\s*5s?\]", " ...\n\n...\n\n... ", text)
    # [PAUSE 3s] -> medium pause (double ellipsis with paragraph break)
    text = re.sub(r"\[PAUSE\s*3s?\]", " ...\n\n... ", text)
    # Catch any other pause markers
    text = re.sub(r"\[PAUSE\s*\d+s?\]", " ...\n\n... ", text)
    return text


async def _gather_mood_context(user_id: str) -> str | None:
    """Get recent mood data for personalization."""
    try:
        _mood_models = sys.modules["zugalife.models"]
    except KeyError:
        return None

    MoodEntry = _mood_models.MoodEntry
    since = datetime.now(timezone.utc) - timedelta(days=3)

    async with get_session() as session:
        result = await session.execute(
            select(MoodEntry)
            .where(
                MoodEntry.user_id == user_id,
                MoodEntry.created_at >= since,
            )
            .order_by(desc(MoodEntry.created_at))
            .limit(5)
        )
        entries = result.scalars().all()

    if not entries:
        return None

    lines = []
    for e in entries:
        label = _prompts._EMOJI_LABELS.get(e.emoji, "")
        line = f"{e.created_at.strftime('%Y-%m-%d')}: {e.emoji} {label}"
        if e.note:
            line += f' — "{e.note[:100]}"'
        lines.append(line)
    return "\n".join(lines)


async def _gather_habit_context(user_id: str) -> str | None:
    """Get recent habit data for personalization."""
    try:
        _habit_models = sys.modules["zugalife.habits.models"]
    except KeyError:
        return None

    HabitDefinition = _habit_models.HabitDefinition
    HabitLog = _habit_models.HabitLog
    since = date.today() - timedelta(days=3)

    async with get_session() as session:
        # Get habit definitions for name lookup
        habits_result = await session.execute(
            select(HabitDefinition)
            .where(HabitDefinition.user_id == user_id)
        )
        habit_map = {h.id: h for h in habits_result.scalars().all()}

        # Get recent logs
        logs_result = await session.execute(
            select(HabitLog)
            .where(
                HabitLog.user_id == user_id,
                HabitLog.log_date >= since,
                HabitLog.completed == True,  # noqa: E712
            )
            .order_by(HabitLog.log_date)
        )
        logs = logs_result.scalars().all()

    if not logs:
        return None

    lines = []
    for log in logs:
        habit = habit_map.get(log.habit_id)
        if habit:
            line = f"{log.log_date}: {habit.emoji} {habit.name}"
            if log.amount and habit.unit:
                line += f" ({log.amount} {habit.unit})"
            lines.append(line)
    return "\n".join(lines) if lines else None


async def _gather_journal_context(user_id: str) -> str | None:
    """Get recent journal themes for personalization."""
    try:
        _journal_models = sys.modules["zugalife.journal.models"]
    except KeyError:
        return None

    JournalEntry = _journal_models.JournalEntry
    since = datetime.now(timezone.utc) - timedelta(days=7)

    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry)
            .where(
                JournalEntry.user_id == user_id,
                JournalEntry.created_at >= since,
            )
            .order_by(desc(JournalEntry.created_at))
            .limit(3)
        )
        entries = result.scalars().all()

    if not entries:
        return None

    lines = []
    for e in entries:
        title = e.title or "Untitled"
        preview = e.content[:150] if e.content else ""
        mood = ""
        if e.mood_emoji:
            label = _prompts._EMOJI_LABELS.get(e.mood_emoji, "")
            mood = f" [{e.mood_emoji} {label}]"
        lines.append(f"{title}{mood}: {preview}")
    return "\n".join(lines)


async def _get_previous_titles(user_id: str) -> list[str]:
    """Get recent session titles to avoid repetition."""
    async with get_session() as session:
        result = await session.execute(
            select(MeditationSession.title)
            .where(MeditationSession.user_id == user_id)
            .order_by(desc(MeditationSession.created_at))
            .limit(5)
        )
        return [row[0] for row in result.all()]
