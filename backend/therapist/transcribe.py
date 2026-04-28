"""ZugaLife therapist transcribe (STT) endpoint.

Wraps OpenAI Whisper for user voice input with budget gating. Mirrors
speech.py — pre-flight `can_spend`, post-success `record_spend` so STT
cost lands in the same ZugaTokens ledger as TTS, chat, and journal AI.

Whisper-1 pricing: $0.006 / minute (rounded to nearest second).
"""

import logging
import sys

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser

logger = logging.getLogger(__name__)

_schemas = sys.modules["zugalife.therapist.schemas"]
TherapistTranscribeResponse = _schemas.TherapistTranscribeResponse

router = APIRouter(prefix="/api/life/therapist", tags=["life-therapist"])

# Whisper-1 official rate. Keep in sync with the value baked into the
# pre-flight estimate below.
_WHISPER_USD_PER_MINUTE = 0.006

# Hard cap so a malicious or buggy client can't upload arbitrary blobs.
# OpenAI's own API caps at 25 MB. ~10 min of compressed mono at low bitrate.
_MAX_AUDIO_BYTES = 25 * 1024 * 1024

# Allowed mimetypes the browser MediaRecorder produces. We don't enforce
# these aggressively (Whisper accepts many formats) — just reject obvious
# non-audio types so we don't burn a Whisper call on garbage.
_ALLOWED_AUDIO_PREFIXES = ("audio/", "video/webm", "video/mp4")


@router.post("/transcribe", response_model=TherapistTranscribeResponse)
async def therapist_transcribe(
    audio: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
) -> TherapistTranscribeResponse:
    """Transcribe a user audio recording via OpenAI Whisper.

    Budget: the pre-flight estimate uses file size (~1 MB ≈ 1 min for typical
    browser webm/opus). If the user has fewer ZugaTokens than the estimate,
    we 402 before calling Whisper. The actual recorded spend uses Whisper's
    reported duration so users only pay for real audio length.
    """
    from app.config import settings
    from core.credits.client import dollars_to_tokens, get_credit_client

    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY missing — /transcribe disabled")
        raise HTTPException(status_code=503, detail="Transcription provider not configured")

    if audio.content_type and not any(
        audio.content_type.startswith(p) for p in _ALLOWED_AUDIO_PREFIXES
    ):
        raise HTTPException(status_code=415, detail=f"Unsupported audio type: {audio.content_type}")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio too large ({len(audio_bytes)} bytes; max {_MAX_AUDIO_BYTES})",
        )

    # Conservative pre-flight estimate. 1 MB compressed ≈ 1 min at typical
    # opus bitrates; if the user is on a higher-bitrate codec we'll just
    # over-reserve credits, which the post-call record_spend reconciles.
    estimated_minutes = max(0.05, len(audio_bytes) / (1024 * 1024))
    estimated_usd = estimated_minutes * _WHISPER_USD_PER_MINUTE
    estimated_tokens = dollars_to_tokens(estimated_usd)
    credit_client = get_credit_client()

    if not await credit_client.can_spend(user.id, user.email, estimated_tokens):
        raise HTTPException(status_code=402, detail="Insufficient ZugaTokens for transcription")

    # Whisper expects a multipart upload with 'file' + 'model' fields.
    # We keep the original filename + content-type so OpenAI's content
    # sniffing works (otherwise it can mis-detect webm).
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                files={"file": (filename, audio_bytes, content_type)},
                data={
                    "model": "whisper-1",
                    "response_format": "verbose_json",  # gives duration
                    "language": "en",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300] if e.response is not None else ""
        logger.warning("therapist.transcribe HTTP %s: %s", e.response.status_code, body)
        if e.response.status_code == 401:
            raise HTTPException(status_code=503, detail="Transcription provider auth failed") from e
        raise HTTPException(status_code=503, detail="Transcription provider unavailable") from e
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("therapist.transcribe provider error: %s", e)
        raise HTTPException(status_code=503, detail="Transcription provider unavailable") from e

    text = (payload.get("text") or "").strip()
    duration_sec = float(payload.get("duration") or 0.0)

    # Whisper-1 bills to nearest second. Compute actual cost from reported
    # duration; fall back to the estimate if the response shape changes.
    actual_minutes = duration_sec / 60.0 if duration_sec > 0 else estimated_minutes
    cost_usd = actual_minutes * _WHISPER_USD_PER_MINUTE

    await credit_client.record_spend(
        user_id=user.id,
        tokens=dollars_to_tokens(cost_usd),
        cost_usd=cost_usd,
        service="openai_whisper",
        reason="therapist_transcribe",
    )

    return TherapistTranscribeResponse(
        text=text,
        duration_sec=duration_sec,
        cost_usd=cost_usd,
    )
