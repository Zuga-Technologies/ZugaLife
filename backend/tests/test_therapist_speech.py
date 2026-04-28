"""Tests for /api/life/therapist/speak endpoint."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def test_speak_returns_mp3_for_valid_text(client: TestClient, mock_user):
    """Happy path: text → MP3 bytes + cost header."""
    from core.ai.providers import TTSResponse

    fake_audio = b"\xff\xfb\x90\x00" + b"\x00" * 1024  # mp3 frame header + padding
    fake_resp = TTSResponse(audio_bytes=fake_audio, model="cartesia/sonic-3", cost_usd=0.0042)

    with patch(
        "core.ai.providers.call_cartesia_tts",
        new=AsyncMock(return_value=fake_resp),
    ), patch(
        "core.credits.client.get_credit_client"
    ) as mock_credits:
        mock_credits.return_value.can_spend = AsyncMock(return_value=True)
        mock_credits.return_value.record_spend = AsyncMock(return_value=None)

        r = client.post(
            "/api/life/therapist/speak",
            json={"text": "Take a slow breath in.", "voice": "calm-female"},
        )

    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["x-tts-cost-usd"] == "0.0042"
    assert r.headers["x-tts-voice"] == "calm-female"
    assert "x-tts-duration-ms" not in r.headers   # not exposed; provider doesn't return duration
    assert r.content == fake_audio


def test_speak_rejects_empty_text(client: TestClient, mock_user):
    r = client.post("/api/life/therapist/speak", json={"text": "", "voice": "calm-female"})
    assert r.status_code == 422


def test_speak_rejects_oversized_text(client: TestClient, mock_user):
    r = client.post(
        "/api/life/therapist/speak",
        json={"text": "a" * 2001, "voice": "calm-female"},
    )
    assert r.status_code == 422


def test_speak_returns_402_on_insufficient_credits(client: TestClient, mock_user):
    with patch("core.credits.client.get_credit_client") as mock_credits:
        mock_credits.return_value.can_spend = AsyncMock(return_value=False)
        r = client.post(
            "/api/life/therapist/speak",
            json={"text": "Take a slow breath in.", "voice": "calm-female"},
        )
    assert r.status_code == 402


def test_speak_returns_503_when_provider_errors(client: TestClient, mock_user):
    """When call_cartesia_tts raises RuntimeError, endpoint returns 503."""
    with patch(
        "core.ai.providers.call_cartesia_tts",
        new=AsyncMock(side_effect=RuntimeError("CARTESIA_API_KEY not configured")),
    ), patch(
        "core.credits.client.get_credit_client"
    ) as mock_credits:
        mock_credits.return_value.can_spend = AsyncMock(return_value=True)
        mock_credits.return_value.record_spend = AsyncMock(return_value=None)

        r = client.post(
            "/api/life/therapist/speak",
            json={"text": "Take a slow breath in.", "voice": "calm-female"},
        )

    assert r.status_code == 503
    # Verify NO spend was recorded (provider errored before we'd charge)
    mock_credits.return_value.record_spend.assert_not_called()
