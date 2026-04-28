"""Tests for /api/life/therapist/speak endpoint."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    """Stub current user dependency."""
    from core.auth.models import CurrentUser
    # DEVIATION from plan: CurrentUser.id is str (not int) and has no supertokens_id field.
    # The conftest also defines mock_user; this local fixture matches the real dataclass API.
    return CurrentUser(id="user-test-1", email="test@example.com")


def test_speak_returns_mp3_for_valid_text(client: TestClient, mock_user):
    """Happy path: text → MP3 bytes + cost header."""
    from core.ai.providers import TTSResponse

    fake_audio = b"\xff\xfb\x90\x00" + b"\x00" * 1024  # mp3 frame header + padding
    fake_resp = TTSResponse(audio=fake_audio, cost_usd=0.0042, duration_ms=1500)

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
