"""ZugaLife meditation endpoints."""

import asyncio
import json
import logging
import struct
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
# StreamingResponse removed — now using background tasks + polling
from sqlalchemy import desc, func, or_, select, update

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.meditation.models"]
_schemas = sys.modules["zugalife.meditation.schemas"]
_prompts = sys.modules["zugalife.meditation.prompts"]

def _get_gam_engine():
    """Lazy lookup — gamification loads after meditation in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

# Pull into globals for FastAPI annotation resolution
MeditationSession = _models.MeditationSession

GenerateRequest = _schemas.GenerateRequest
MoodAfterRequest = _schemas.MoodAfterRequest
SessionResponse = _schemas.SessionResponse
SessionBrief = _schemas.SessionBrief
SessionListResponse = _schemas.SessionListResponse
RemainingResponse = _schemas.RemainingResponse

DAILY_LIMIT = _prompts.DAILY_SESSION_LIMIT

# Cartesia voice UUID map — maps user-facing voice names to Cartesia voice IDs.
# Browse voices at https://play.cartesia.ai/
CARTESIA_VOICE_MAP: dict[str, str] = {
    "serene": "cd17ff2d-5ea4-4695-be8f-42193949b946",   # Meditation Lady
    "gentle": "00a77add-48d5-4ef6-8157-71e5437b282d",   # Calm Lady
    "whisper": "03496517-369a-4db1-8236-3d3ae459ddf7",   # ASMR Lady
}

# OpenAI fallback map (when Cartesia is not configured)
OPENAI_VOICE_MAP: dict[str, str] = {
    "serene": "shimmer",
    "gentle": "shimmer",
    "whisper": "nova",
}

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


@router.post("/generate", response_model=SessionResponse, status_code=202)
async def generate_meditation(
    body: GenerateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Start meditation generation in the background.

    Returns immediately with a session stub (status="generating").
    The client polls GET /sessions/{id} until status becomes "ready" or "failed".
    Generation survives client disconnects and page refreshes.
    """
    # Block duplicate generation — only one at a time per user
    # Auto-fail stuck sessions (>10 min) so they don't block forever
    async with get_session() as session:
        in_progress = await session.execute(
            select(MeditationSession).where(
                MeditationSession.user_id == user.id,
                MeditationSession.status == "generating",
            )
        )
        existing = in_progress.scalar_one_or_none()
        if existing:
            age = datetime.now(timezone.utc) - existing.created_at.replace(tzinfo=timezone.utc)
            if age.total_seconds() > 600:
                # Stuck — auto-fail it so user can try again
                await session.execute(
                    update(MeditationSession)
                    .where(MeditationSession.id == existing.id)
                    .values(status="failed", error_message="Generation timed out")
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail="A meditation is already being generated. Please wait for it to finish.",
                )

    used = await _sessions_today(user.id)
    if used >= DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've used all {DAILY_LIMIT} meditation sessions today. Come back tomorrow.",
        )

    try:
        from core.ai.gateway import ai_call
        from core.ai.providers import call_cartesia_tts, call_openai_tts
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Meditation generation not available in standalone mode",
        )

    # Create a placeholder session immediately
    async with get_session() as session:
        meditation = MeditationSession(
            user_id=user.id,
            type=body.type.value,
            length=body.length.value,
            duration_seconds=0,
            ambience=body.ambience.value,
            voice=body.voice.value,
            focus=body.focus,
            title="Generating...",
            transcript="",
            audio_filename="",
            model_used="",
            tts_model="",
            cost=0.0,
            status="generating",
        )
        session.add(meditation)
        await session.flush()
        await session.refresh(meditation)
        session_id = meditation.id

    # Fire off background generation
    asyncio.create_task(_generate_in_background(
        session_id=session_id,
        user_id=user.id,
        user_email=user.email,
        body=body,
        ai_call=ai_call,
        call_openai_tts=call_openai_tts,
        call_cartesia_tts=call_cartesia_tts,
    ))

    logger.info("Meditation %d queued for user=%s length=%s", session_id, user.id, body.length.value)

    # Return the stub — frontend polls until status="ready"
    async with get_session() as session:
        result = await session.execute(
            select(MeditationSession).where(MeditationSession.id == session_id)
        )
        return SessionResponse.model_validate(result.scalar_one())


async def _generate_in_background(
    session_id: int,
    user_id: str,
    user_email: str,
    body: GenerateRequest,
    ai_call,
    call_openai_tts,
    call_cartesia_tts=None,
):
    """Run the full LLM + TTS pipeline in a background task.

    Updates the DB session row as it progresses. On failure, sets
    status='failed' with an error_message. On success, sets status='ready'
    with all generated content.
    """
    total_cost = 0.0

    try:
        # 1. Gather personalization context
        mood_ctx = await _gather_mood_context(user_id)
        habit_ctx = await _gather_habit_context(user_id)
        journal_ctx = await _gather_journal_context(user_id)
        prev_titles = await _get_previous_titles(user_id)

        # 2. Generate script
        from meditation.prompts import _MAX_TOKENS
        script_max_tokens = _MAX_TOKENS.get(body.length.value, 3000)
        is_long = body.length.value == "long"

        if is_long:
            # Pass 1: Outline
            outline_prompt = _prompts.build_outline_prompt(
                meditation_type=body.type.value,
                length=body.length.value,
                focus=body.focus,
                mood_context=mood_ctx,
                habit_context=habit_ctx,
                journal_context=journal_ctx,
                previous_titles=prev_titles,
            )
            outline_response = await ai_call(
                outline_prompt, task="creative", max_tokens=2048,
                user_id=user_id, user_email=user_email,
            )
            total_cost += outline_response.cost

            outline = outline_response.content.strip()
            section_count = outline.count("## ")
            if section_count < 2:
                section_count = 6
            print(f"[MEDITATION] {session_id} outline done, {section_count} sections", flush=True)

            # Pass 2: Expand
            expansion_prompt = _prompts.build_expansion_prompt(outline, section_count)
            script_response = await ai_call(
                expansion_prompt, task="creative_long", max_tokens=script_max_tokens,
                user_id=user_id, user_email=user_email,
            )
            total_cost += script_response.cost
            print(f"[MEDITATION] {session_id} expansion done, {len(script_response.content.split())} words", flush=True)
        else:
            # Single-pass
            prompt = _prompts.build_meditation_prompt(
                meditation_type=body.type.value,
                length=body.length.value,
                focus=body.focus,
                mood_context=mood_ctx,
                habit_context=habit_ctx,
                journal_context=journal_ctx,
                previous_titles=prev_titles,
            )
            script_response = await ai_call(
                prompt, task="creative", max_tokens=script_max_tokens,
                user_id=user_id, user_email=user_email,
            )
            total_cost += script_response.cost

        raw_script = script_response.content.strip()
        title, transcript = _parse_script(raw_script)

        # 3. TTS — split on pause markers, render segments, inject real silence
        segments = _split_on_pauses(transcript)
        print(f"[MEDITATION] {session_id} TTS starting, {len(segments)} segments", flush=True)

        try:
            from app.config import settings as _settings
            _use_cartesia = (
                call_cartesia_tts is not None
                and getattr(_settings, "cartesia_api_key", "")
            )
        except ImportError:
            _use_cartesia = False

        # Render each segment, then merge with ffmpeg for proper MP3 structure
        import shutil
        import subprocess
        import tempfile

        tts_cost = 0.0
        tts_provider = "cartesia" if _use_cartesia else "openai"
        tmp_dir = Path(tempfile.mkdtemp(prefix="meditation_"))
        part_files: list[Path] = []

        try:
            for i, (seg_text, silence_secs) in enumerate(segments):
                if not seg_text.strip():
                    if silence_secs > 0:
                        sf = tmp_dir / f"part_{len(part_files):04d}_silence.mp3"
                        sf.write_bytes(_generate_silence_mp3(silence_secs))
                        part_files.append(sf)
                    continue

                print(f"[MEDITATION] {session_id} segment {i+1}/{len(segments)}, {len(seg_text)} chars, {silence_secs}s pause after", flush=True)

                if _use_cartesia:
                    cartesia_voice_id = CARTESIA_VOICE_MAP.get(body.voice.value, CARTESIA_VOICE_MAP["serene"])
                    seg_tts = await call_cartesia_tts(
                        text=seg_text, voice_id=cartesia_voice_id, speed=0.75, emotion="calm",
                    )
                else:
                    openai_voice = OPENAI_VOICE_MAP.get(body.voice.value, "shimmer")
                    seg_tts = await call_openai_tts(
                        text=seg_text, voice=openai_voice, speed=0.9,
                    )

                vf = tmp_dir / f"part_{len(part_files):04d}_voice.mp3"
                vf.write_bytes(seg_tts.audio_bytes)
                part_files.append(vf)
                tts_cost += seg_tts.cost

                if silence_secs > 0:
                    sf = tmp_dir / f"part_{len(part_files):04d}_silence.mp3"
                    sf.write_bytes(_generate_silence_mp3(silence_secs))
                    part_files.append(sf)

            # Merge all parts with ffmpeg
            if len(part_files) == 1:
                merged_audio = part_files[0].read_bytes()
            else:
                concat_list = tmp_dir / "concat.txt"
                concat_list.write_text("\n".join(f"file '{f.name}'" for f in part_files))
                output_path = tmp_dir / "merged.mp3"
                merge_result = subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", str(concat_list), "-c:a", "libmp3lame", "-b:a", "128k",
                     str(output_path)],
                    capture_output=True, timeout=120,
                )
                if merge_result.returncode != 0:
                    print(f"[MEDITATION] {session_id} ffmpeg failed: {merge_result.stderr.decode()[:300]}", flush=True)
                    merged_audio = bytearray()
                    for f in part_files:
                        merged_audio.extend(f.read_bytes())
                    merged_audio = bytes(merged_audio)
                else:
                    merged_audio = output_path.read_bytes()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        total_cost += tts_cost

        class _AudioResult:
            audio_bytes = merged_audio
            cost = tts_cost
        tts_result = _AudioResult()
        print(f"[MEDITATION] {session_id} TTS done, {len(tts_result.audio_bytes)} bytes, provider={tts_provider}", flush=True)

        actual_seconds = int(_mp3_duration_seconds(tts_result.audio_bytes))

        # 4. Save audio file
        user_dir = _AUDIO_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        temp_filename = f"{int(time.time())}_{body.type.value}.mp3"
        audio_path = user_dir / temp_filename
        audio_path.write_bytes(tts_result.audio_bytes)

        # 5. Update DB row to "ready"
        async with get_session() as session:
            await session.execute(
                update(MeditationSession)
                .where(MeditationSession.id == session_id)
                .values(
                    title=title,
                    transcript=transcript,
                    audio_filename=f"{user_id}/{temp_filename}",
                    model_used=script_response.model,
                    tts_model=tts_result.model,
                    cost=total_cost,
                    duration_seconds=actual_seconds,
                    status="ready",
                )
            )

        print(f"[MEDITATION] {session_id} READY: {body.type.value} {body.length.value} {actual_seconds}s ${total_cost:.4f} {title!r}", flush=True)
        # XP is awarded when the user finishes listening (POST /sessions/{id}/complete)

    except Exception as e:
        print(f"[MEDITATION] {session_id} FAILED: {type(e).__name__}: {e}", flush=True)
        try:
            async with get_session() as session:
                await session.execute(
                    update(MeditationSession)
                    .where(MeditationSession.id == session_id)
                    .values(
                        status="failed",
                        error_message=f"{type(e).__name__}: {str(e)[:400]}",
                    )
                )
        except Exception as e2:
            print(f"[MEDITATION] {session_id} failed to update status: {e2}", flush=True)


# --- CRUD ---


@router.get("/in-progress")
async def get_in_progress(user: CurrentUser = Depends(get_current_user)):
    """Return the currently-generating session, if any. Used by frontend to
    resume polling after page refresh / navigation.

    Auto-fails sessions stuck generating for >10 minutes.
    """
    async with get_session() as session:
        result = await session.execute(
            select(MeditationSession).where(
                MeditationSession.user_id == user.id,
                MeditationSession.status == "generating",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"session": None}

        # Auto-fail stuck sessions (>10 min)
        age = datetime.now(timezone.utc) - row.created_at.replace(tzinfo=timezone.utc)
        if age.total_seconds() > 600:
            await session.execute(
                update(MeditationSession)
                .where(MeditationSession.id == row.id)
                .values(status="failed", error_message="Generation timed out")
            )
            return {"session": None}

        return {"session": SessionResponse.model_validate(row).model_dump()}


@router.post("/generate-script")
async def generate_script(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate a meditation script via the AI gateway (GPT-4o).

    Used by the Chrome extension for the LLM step only.
    """
    try:
        from core.ai.gateway import ai_call
    except ImportError:
        raise HTTPException(status_code=503, detail="AI gateway not available")

    prompt = body.get("prompt", "")
    max_tokens = body.get("max_tokens", 3000)
    task = body.get("task", "creative")

    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

    response = await ai_call(
        prompt, task=task, max_tokens=max_tokens,
        user_id=user.id, user_email=user.email,
    )

    return {
        "content": response.content,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost": response.cost,
    }


@router.post("/generate-from-script")
async def generate_from_script(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """Take a pre-generated script and run TTS + stitching server-side.

    The extension generates the script (expensive LLM call via proxy),
    then hands it to the server for TTS + audio stitching (proven pipeline).
    Returns a complete session with audio, ready to play on any device.
    """
    script = body.get("script", "")
    med_type = body.get("type", "breathing")
    length = body.get("length", "medium")
    ambience = body.get("ambience", "silence")
    voice = body.get("voice", "serene")
    focus = body.get("focus", "")
    script_cost = body.get("script_cost", 0.0)

    if not script or len(script.strip()) < 50:
        raise HTTPException(status_code=400, detail="Script too short")

    try:
        from core.ai.providers import call_openai_tts, call_cartesia_tts
    except ImportError:
        raise HTTPException(status_code=503, detail="TTS not available")

    # Parse script
    title, transcript = _parse_script(script)

    # If the LLM didn't include pause markers, inject them at sentence boundaries
    import re
    pause_count = len(re.findall(r"\[PAUSE\s*\d+s?\]", transcript, re.IGNORECASE))
    if pause_count < 5:
        print(f"[MEDITATION] Script has only {pause_count} pause markers, injecting at sentence boundaries")
        # Insert [PAUSE 3s] after every 2-3 sentences (roughly every 100-150 chars)
        sentences = re.split(r'(?<=[.!?])\s+', transcript)
        rebuilt = []
        for i, sentence in enumerate(sentences):
            rebuilt.append(sentence)
            if (i + 1) % 2 == 0 and i < len(sentences) - 1:
                rebuilt.append("[PAUSE 3s]")
            if (i + 1) % 6 == 0 and i < len(sentences) - 1:
                rebuilt[-1] = "[PAUSE 5s]"  # Replace every 3rd pause with a longer one
        transcript = " ".join(rebuilt)

    # TTS + stitch
    segments = _split_on_pauses(transcript)

    try:
        from app.config import settings as _settings
        _use_cartesia = bool(getattr(_settings, "cartesia_api_key", ""))
    except ImportError:
        _use_cartesia = False

    import shutil
    import subprocess
    import tempfile

    tts_cost = 0.0
    tts_provider = "cartesia" if _use_cartesia else "openai"
    tmp_dir = Path(tempfile.mkdtemp(prefix="meditation_"))
    part_files: list[Path] = []

    try:
        for i, (seg_text, silence_secs) in enumerate(segments):
            if not seg_text.strip():
                if silence_secs > 0:
                    sf = tmp_dir / f"part_{len(part_files):04d}_silence.mp3"
                    sf.write_bytes(_generate_silence_mp3(silence_secs))
                    part_files.append(sf)
                continue

            if _use_cartesia:
                cartesia_voice_id = CARTESIA_VOICE_MAP.get(voice, CARTESIA_VOICE_MAP["serene"])
                tts_result = await call_cartesia_tts(
                    text=seg_text, voice_id=cartesia_voice_id, speed=0.75, emotion="calm",
                )
            else:
                openai_voice = OPENAI_VOICE_MAP.get(voice, "shimmer")
                tts_result = await call_openai_tts(
                    text=seg_text, voice=openai_voice, speed=0.9,
                )

            vf = tmp_dir / f"part_{len(part_files):04d}_voice.mp3"
            vf.write_bytes(tts_result.audio_bytes)
            part_files.append(vf)
            tts_cost += tts_result.cost

            if silence_secs > 0:
                sf = tmp_dir / f"part_{len(part_files):04d}_silence.mp3"
                sf.write_bytes(_generate_silence_mp3(silence_secs))
                part_files.append(sf)

        # Merge all parts with ffmpeg (handles headers, sample rates, everything)
        if len(part_files) == 1:
            audio_bytes = part_files[0].read_bytes()
        else:
            concat_list = tmp_dir / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{f.name}'" for f in part_files),
            )
            output_path = tmp_dir / "merged.mp3"
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list),
                    "-c:a", "libmp3lame", "-b:a", "128k",
                    str(output_path),
                ],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                print(f"[MEDITATION] ffmpeg failed: {result.stderr.decode()[:500]}")
                # Fallback: raw concat (broken but at least produces something)
                raw = bytearray()
                for f in part_files:
                    raw.extend(f.read_bytes())
                audio_bytes = bytes(raw)
            else:
                audio_bytes = output_path.read_bytes()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    actual_seconds = int(_mp3_duration_seconds(audio_bytes))

    # Save audio
    user_dir = _AUDIO_DIR / user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    temp_filename = f"{int(time.time())}_{med_type}.mp3"
    audio_path = user_dir / temp_filename
    audio_path.write_bytes(audio_bytes)

    # Create session
    total_cost = script_cost + tts_cost
    async with get_session() as session:
        meditation = MeditationSession(
            user_id=user.id,
            type=med_type,
            length=length,
            duration_seconds=actual_seconds,
            ambience=ambience,
            voice=voice,
            focus=focus or None,
            title=title,
            transcript=transcript,
            audio_filename=f"{user.id}/{temp_filename}",
            model_used=body.get("model", "gpt-4o"),
            tts_model=tts_provider,
            cost=total_cost,
            status="ready",
        )
        session.add(meditation)
        await session.flush()
        result = await session.execute(
            select(MeditationSession).where(MeditationSession.id == meditation.id)
        )
        return SessionResponse.model_validate(result.scalar_one())


@router.post("/upload")
async def upload_meditation(
    audio: UploadFile,
    title: str = Form(...),
    transcript: str = Form(...),
    type: str = Form(...),
    length: str = Form("medium"),
    ambience: str = Form("silence"),
    voice: str = Form("serene"),
    focus: str = Form(""),
    model_used: str = Form(""),
    tts_model: str = Form("tts-1-hd"),
    cost: float = Form(0.0),
    duration_seconds: int = Form(0),
    user: CurrentUser = Depends(get_current_user),
):
    """Accept a meditation MP3 uploaded from the Chrome extension.

    Creates a MeditationSession record so the meditation appears across all
    devices. The extension generates audio locally (via server-proxied API
    calls) and uploads the finished file here for cross-device sync.
    """
    # Save audio file
    user_dir = _AUDIO_DIR / user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    temp_filename = f"{int(time.time())}_{type}.mp3"
    audio_path = user_dir / temp_filename
    audio_bytes = await audio.read()
    audio_path.write_bytes(audio_bytes)

    # Calculate duration from audio if not provided
    if duration_seconds <= 0:
        duration_seconds = int(_mp3_duration_seconds(audio_bytes))

    # Create session record
    async with get_session() as session:
        meditation = MeditationSession(
            user_id=user.id,
            type=type,
            length=length,
            duration_seconds=duration_seconds,
            ambience=ambience,
            voice=voice,
            focus=focus or None,
            title=title,
            transcript=transcript,
            audio_filename=f"{user.id}/{temp_filename}",
            model_used=model_used,
            tts_model=tts_model,
            cost=cost,
            status="ready",
        )
        session.add(meditation)
        await session.flush()
        result = await session.execute(
            select(MeditationSession).where(MeditationSession.id == meditation.id)
        )
        return SessionResponse.model_validate(result.scalar_one())


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: CurrentUser = Depends(get_current_user),
):
    """List past meditation sessions (most recent first). Excludes in-progress."""
    async with get_session() as session:
        # Show ready + legacy (NULL status) sessions, hide generating/failed
        ready_filter = or_(
            MeditationSession.status == "ready",
            MeditationSession.status.is_(None),
        )

        count_result = await session.execute(
            select(func.count())
            .select_from(MeditationSession)
            .where(
                MeditationSession.user_id == user.id,
                ready_filter,
            )
        )
        total = count_result.scalar_one()

        result = await session.execute(
            select(MeditationSession)
            .where(
                MeditationSession.user_id == user.id,
                ready_filter,
            )
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


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Mark a meditation session as completed (user listened through).

    Awards XP and triggers challenge completion. Idempotent — calling
    again on an already-completed session returns it without re-awarding.
    """
    async with get_session() as db:
        meditation = await _get_user_session(db, session_id, user.id)

        if meditation.completed_at:
            return SessionResponse.model_validate(meditation)

        meditation.completed_at = datetime.now(timezone.utc)
        await db.flush()

        gam = _get_gam_engine()
        logger.info("Meditation complete: session=%d gam_engine=%s", session_id, gam is not None)
        if gam:
            try:
                result = await gam.award_xp(
                    db, user_id=user.id,
                    source="meditation_complete",
                    description=f"Completed {meditation.type} meditation ({meditation.duration_seconds // 60}min)",
                )
                logger.info("Meditation XP awarded: %s", result)
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

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
    """Count how many sessions a user has successfully generated today.

    Only counts sessions with status 'ready' — stuck or failed
    generations don't count against the daily limit.
    """
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
                MeditationSession.status == "ready",
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
    """Clean transcript text for TTS — converts digits to words.

    Pause markers are handled separately by _split_on_pauses() which
    splits the transcript into segments with silence durations between them.
    """
    import re

    _DIGIT_WORDS = {
        "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
        "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
    }
    text = transcript
    for digit, word in _DIGIT_WORDS.items():
        text = re.sub(rf"\b{digit}\b", word, text)

    # Strip pause markers (they're handled by _split_on_pauses)
    text = re.sub(r"\[PAUSE\s*\d+s?\]", " ... ", text)
    return text


def _split_on_pauses(transcript: str) -> list[tuple[str, int]]:
    """Split transcript into (text_segment, silence_after_seconds) pairs.

    Returns segments of text with the number of seconds of silence
    to insert after each segment. Last segment has 0 silence.
    """
    import re

    _DIGIT_WORDS = {
        "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
        "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
    }

    # Find all pause markers and their positions
    pattern = re.compile(r"\[PAUSE\s*(\d+)s?\]")
    segments: list[tuple[str, int]] = []
    last_end = 0

    for match in pattern.finditer(transcript):
        text_chunk = transcript[last_end:match.start()].strip()
        silence_secs = int(match.group(1))
        if text_chunk:
            # Convert digits in this chunk
            for digit, word in _DIGIT_WORDS.items():
                text_chunk = re.sub(rf"\b{digit}\b", word, text_chunk)
            segments.append((text_chunk, silence_secs))
        last_end = match.end()

    # Remainder after last pause marker
    remainder = transcript[last_end:].strip()
    if remainder:
        for digit, word in _DIGIT_WORDS.items():
            remainder = re.sub(rf"\b{digit}\b", word, remainder)
        segments.append((remainder, 0))

    # If no pause markers found, return the whole thing
    if not segments:
        text = transcript
        for digit, word in _DIGIT_WORDS.items():
            text = re.sub(rf"\b{digit}\b", word, text)
        segments.append((text, 0))

    return segments


def _generate_silence_mp3(seconds: float, bitrate: int = 128000) -> bytes:
    """Generate silent MP3 frames for the given duration.

    Creates a valid MP3 byte sequence of silence by repeating a minimal
    silent MPEG1 Layer III frame. Each frame is 417 bytes at 128kbps/44100Hz
    and lasts ~26.1ms (1152 samples / 44100 Hz).
    """
    # Minimal valid silent MP3 frame (MPEG1, Layer III, 128kbps, 44100Hz, stereo)
    # Frame header: 0xFFFB9004 + 413 zero bytes = silent frame
    frame_header = bytes([
        0xFF, 0xFB, 0x90, 0x04,  # MPEG1, Layer III, 128kbps, 44100Hz, stereo
    ])
    frame_data = b'\x00' * 413  # Silent audio data to fill frame (417 total)
    silent_frame = frame_header + frame_data

    # Each frame = 1152 samples at 44100Hz = 26.122ms
    frames_needed = int(seconds * 44100 / 1152) + 1
    return silent_frame * frames_needed


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
