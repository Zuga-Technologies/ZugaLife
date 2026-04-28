"""ZugaLife therapist speech (TTS) endpoint.

Wraps Cartesia TTS for assistant utterances with budget gating.
Mirrors the pattern used in meditation/routes.py — buffered MP3 response.
Streaming WebSocket TTS is intentionally out of scope for the MVP.
"""

import logging
import sys

from fastapi import APIRouter, Depends, HTTPException, Response

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser

logger = logging.getLogger(__name__)

_schemas = sys.modules["zugalife.therapist.schemas"]
TherapistSpeakRequest = _schemas.TherapistSpeakRequest

router = APIRouter(prefix="/api/life/therapist", tags=["life-therapist"])


@router.post(
    "/speak",
    responses={
        200: {"content": {"audio/mpeg": {}}, "description": "MP3 audio bytes"},
        402: {"description": "Insufficient credits"},
        503: {"description": "TTS provider unavailable"},
    },
)
async def therapist_speak(
    body: TherapistSpeakRequest,
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Synthesize an assistant utterance to MP3 via Cartesia.

    Budget: pre-flight `can_spend`, post-success `record_spend`. Errors return
    402 (no credits), 503 (provider down), or 500 (unexpected).

    "cartesia-sonic-3" is not in the model registry and would fall back to the
    same default rate — using the canonical "tts-1-hd" is explicit and matches
    meditation/routes.py L296.
    """
    from core.ai.providers import call_cartesia_tts
    from core.credits.client import get_credit_client, dollars_to_tokens
    from core.gateway.providers import estimate_tts_cost

    estimated_usd = estimate_tts_cost(len(body.text), "tts-1-hd")
    estimated_tokens = dollars_to_tokens(estimated_usd)
    credit_client = get_credit_client()

    if not await credit_client.can_spend(user.id, user.email, estimated_tokens):
        raise HTTPException(status_code=402, detail="Insufficient ZugaTokens for voice")

    try:
        tts = await call_cartesia_tts(
            text=body.text,
            voice_id=body.voice,
            speed=1.0,
            emotion="warm",
        )
    except RuntimeError as e:
        logger.warning("therapist.speak provider error: %s", e)
        raise HTTPException(status_code=503, detail="Voice provider unavailable") from e

    await credit_client.record_spend(
        user_id=user.id,
        tokens=dollars_to_tokens(tts.cost_usd),
        cost_usd=tts.cost_usd,
        service="cartesia",
        reason="therapist_speech",
    )

    return Response(
        content=tts.audio_bytes,
        media_type="audio/mpeg",
        headers={
            "x-tts-cost-usd": f"{tts.cost_usd:.4f}",
            "x-tts-voice": body.voice,
        },
    )
