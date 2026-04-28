"""Test configuration for ZugaLife wellness-avatar backend.

sys.path strategy:
  ZugaLife/backend is prepended so that `core` resolves to ZugaLife/core,
  which has symlinks to ZugaCore for auth/, credits/, and gateway/.
  The local backend/ is appended after so plugin.py and therapist/ are findable.

core.ai.providers is injected synthetically — it does not exist in ZugaLife/core
(that package only has auth/credits/gateway). The injected module exposes TTSResponse
and call_cartesia_tts stubs that match what speech.py and the tests expect.
"""

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ── sys.path setup ───────────────────────────────────────────────────────────
# MUST happen before any core.* imports so the right package tree is resolved.

_BACKEND_DIR = str(Path(__file__).parent.parent)          # .../ZugaLife-wellness-avatar/backend
_ZUGALIFE_BACKEND = str(Path(__file__).parent.parent.parent.parent / "ZugaLife" / "backend")

# ZugaLife/backend first so core = ZugaLife/core (has auth/credits/gateway symlinks)
if _ZUGALIFE_BACKEND not in sys.path:
    sys.path.insert(0, _ZUGALIFE_BACKEND)
# Local backend second so plugin.py / therapist/ are importable
if _BACKEND_DIR not in sys.path:
    sys.path.append(_BACKEND_DIR)

# ── Inject core.ai.providers ─────────────────────────────────────────────────
# ZugaLife/core has no ai/ subpackage. We create a synthetic module so that:
#   from core.ai.providers import TTSResponse, call_cartesia_tts
# resolves consistently across speech.py and the test mocks.

@dataclass
class TTSResponse:
    """Buffered TTS result — used by the therapist speak endpoint."""
    audio: bytes
    cost_usd: float
    duration_ms: int


async def call_cartesia_tts(text: str, voice_id: str = "", speed: float = 1.0, emotion: str = "warm") -> TTSResponse:
    """Stub — always replaced by test mocks; never called in production tests."""
    raise RuntimeError("call_cartesia_tts stub should be mocked in tests")


_ai_providers_mod = types.ModuleType("core.ai.providers")
_ai_providers_mod.TTSResponse = TTSResponse
_ai_providers_mod.call_cartesia_tts = call_cartesia_tts

# Register as core.ai.providers AND ensure core.ai package exists
if "core.ai" not in sys.modules:
    _ai_pkg = types.ModuleType("core.ai")
    _ai_pkg.__path__ = []
    _ai_pkg.__package__ = "core.ai"
    sys.modules["core.ai"] = _ai_pkg

sys.modules["core.ai.providers"] = _ai_providers_mod

# ── Ensure core.gateway.providers is importable ──────────────────────────────
# ZugaLife/core has gateway/ — it's accessible when ZugaLife/backend is on sys.path.
# Force-load it now so later `from core.gateway.providers import estimate_tts_cost`
# works inside speech.py even though `core` package was already bound.

import importlib as _importlib

if "core.gateway" not in sys.modules:
    _core_mod = sys.modules.get("core")
    _gw_path = Path(_ZUGALIFE_BACKEND).parent / "core" / "gateway"
    _gw_pkg = types.ModuleType("core.gateway")
    _gw_pkg.__path__ = [str(_gw_path)]
    _gw_pkg.__package__ = "core.gateway"
    if _core_mod is not None:
        _core_mod.gateway = _gw_pkg
    sys.modules["core.gateway"] = _gw_pkg

if "core.gateway.providers" not in sys.modules:
    import importlib.util as _ilu2
    _gw_providers_path = Path(_ZUGALIFE_BACKEND).parent / "core" / "gateway" / "providers.py"
    _gw_spec = _ilu2.spec_from_file_location("core.gateway.providers", _gw_providers_path)
    _gw_mod = _ilu2.module_from_spec(_gw_spec)
    sys.modules["core.gateway.providers"] = _gw_mod
    _gw_spec.loader.exec_module(_gw_mod)
    sys.modules["core.gateway"].providers = _gw_mod

# ── Pre-register zugalife.therapist.schemas ──────────────────────────────────
# speech.py reads TherapistSpeakRequest from sys.modules["zugalife.therapist.schemas"]
# at import time. We pre-load the real schemas module so the lookup succeeds.

import importlib.util as _ilu

_schemas_path = Path(_BACKEND_DIR) / "therapist" / "schemas.py"
_schemas_spec = _ilu.spec_from_file_location("zugalife.therapist.schemas", _schemas_path)
_schemas_mod = _ilu.module_from_spec(_schemas_spec)
sys.modules["zugalife.therapist.schemas"] = _schemas_mod
_schemas_spec.loader.exec_module(_schemas_mod)

# ── Test app factory ─────────────────────────────────────────────────────────

def _make_app(current_user):
    """Build a minimal FastAPI app with only the speech router registered.

    We do NOT use plugin.py here — it pulls in 20+ submodules (SQLAlchemy
    models, DB sessions, etc.) which are unnecessary for unit tests. Speech
    is a pure HTTP handler; we only need its router + a stubbed auth dependency.
    """
    from fastapi import FastAPI
    from core.auth.middleware import get_current_user

    # Import the speech module (it reads TherapistSpeakRequest from sys.modules)
    import importlib.util as ilu
    _speech_path = Path(_BACKEND_DIR) / "therapist" / "speech.py"
    _speech_spec = ilu.spec_from_file_location("zugalife.therapist.speech", _speech_path)
    _speech_mod = ilu.module_from_spec(_speech_spec)
    sys.modules["zugalife.therapist.speech"] = _speech_mod
    _speech_spec.loader.exec_module(_speech_mod)

    app = FastAPI()
    app.include_router(_speech_mod.router)

    # Override auth so no token is needed
    app.dependency_overrides[get_current_user] = lambda: current_user

    return app


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_user():
    """Stub current user dependency."""
    from core.auth.models import CurrentUser
    # CurrentUser.id is str in the real model; plan uses int=1 for brevity.
    # We pass str to match the model and avoid type errors inside speech.py.
    return CurrentUser(id="user-test-1", email="test@example.com")


@pytest.fixture
def client(mock_user):
    """FastAPI TestClient with speech router and stubbed auth."""
    from fastapi.testclient import TestClient
    app = _make_app(mock_user)
    return TestClient(app)
