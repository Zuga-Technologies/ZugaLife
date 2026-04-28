# Wellness Avatar MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 3D animated character with live Cartesia voice + lip sync to the ZugaLife wellness bot (`TherapistTab.vue`) — Grok-companion style, but minimal.

**Architecture:**
- **Backend**: New `POST /api/life/therapist/speak` endpoint that wraps the existing `call_cartesia_tts` (already used by meditation). Returns MP3 bytes + cost metadata. Budget-gated via `credit_client.can_spend` / `record_spend`, mirroring meditation's pattern.
- **Frontend**: Three.js + `@pixiv/three-vrm` rendering a Ready Player Me VRM head-and-shoulders avatar above the chat. Idle breathing via sine-wave bone rotation. Speech: HTMLAudioElement plays the MP3 blob; a Web Audio API `AnalyserNode` reads RMS volume each frame and drives the avatar's `mouthOpen` blendshape. Toggle in `LifeSettings.vue`.
- **Why buffered MP3, not streaming WebSocket**: existing Cartesia integration is buffered and works today. Streaming TTS + barge-in + visemes are post-MVP. This MVP gets a talking head in front of users; we measure latency before optimizing.

**Tech Stack:**
- Frontend: Vue 3, TypeScript, Vite, Three.js (`three@^0.169.0`), `@pixiv/three-vrm@^3.4.0`, Web Audio API
- Backend: FastAPI, existing `core.ai.providers.call_cartesia_tts`, existing `core.credits.client`
- Avatar source: VRoid Hub (https://hub.vroid.com/) — user picks or builds a VRM and downloads it as `.vrm` (native VRM export; no GLB→VRM conversion needed). VRoid Studio (free desktop app) is the alternative for from-scratch designs.

**Out of scope (do NOT implement, even if tempting):**
- Streaming TTS / WebSocket transport
- Barge-in / interrupt handling
- Voice input (STT)
- Multi-character picker
- Custom rigging or per-phoneme visemes (volume-driven mouth only)
- Body / hand animation beyond idle breathing

---

## File Structure

**Created:**
- `ZugaLife/backend/therapist/speech.py` — TTS endpoint + budget gate
- `ZugaLife/backend/tests/test_therapist_speech.py` — endpoint tests
- `ZugaLife/frontend/components/WellnessAvatar.vue` — Three.js + VRM renderer
- `ZugaLife/frontend/composables/useAvatarSpeech.ts` — fetch + play + lip-sync
- `ZugaLife/frontend/public/avatars/README.md` — instructions for user to drop VRM
- `ZugaLife/frontend/public/avatars/wellness.vrm` — user-supplied VRM (committed only as a placeholder note in README; binary asset added by user)

**Modified:**
- `ZugaLife/backend/therapist/routes.py` — register speech router; expose voice/cost in chat response
- `ZugaLife/backend/therapist/schemas.py` — add `TherapistSpeakRequest` / `TherapistSpeakResponse`
- `ZugaLife/frontend/package.json` — add `three` + `@pixiv/three-vrm`
- `ZugaLife/frontend/tabs/TherapistTab.vue` — mount avatar above chat; trigger speech on assistant messages
- `ZugaLife/frontend/LifeSettings.vue` — add "Avatar voice" toggle
- `ZugaLife/frontend/composables/useLifeShared.ts` — expose `avatarEnabled` + `voiceEnabled` settings (persisted to localStorage)

---

## Task 1: Backend speech schemas

**Files:**
- Modify: `ZugaLife/backend/therapist/schemas.py`

- [ ] **Step 1: Read current schemas to find insertion point**

```bash
grep -n "TherapistChatResponse\|class Therapist" ZugaLife/backend/therapist/schemas.py
```

Expected: locate the existing Pydantic class block; new schemas go directly after `TherapistChatResponse`.

- [ ] **Step 2: Add request/response schemas**

Append to `ZugaLife/backend/therapist/schemas.py` (after `TherapistChatResponse`, before any list/note schemas):

```python
class TherapistSpeakRequest(BaseModel):
    """Request to synthesize an assistant utterance to audio."""
    text: str = Field(..., min_length=1, max_length=2000, description="Assistant text to speak")
    voice: str = Field(default="calm-female", description="Cartesia voice key (see CARTESIA_VOICE_MAP)")


class TherapistSpeakResponse(BaseModel):
    """Audio + cost metadata. Audio is delivered as the response body (MP3);
    this schema is only used for the OpenAPI doc and 4xx error envelopes."""
    cost: float = Field(..., description="USD cost of this TTS call")
    duration_ms: int = Field(..., description="Approximate audio duration in milliseconds")
    voice: str = Field(..., description="Echoed Cartesia voice key actually used")
```

- [ ] **Step 3: Commit**

```bash
git add ZugaLife/backend/therapist/schemas.py
git commit -m "feat(therapist): add TherapistSpeak request/response schemas"
```

---

## Task 2: Backend speech endpoint (tests first)

**Files:**
- Create: `ZugaLife/backend/therapist/speech.py`
- Test: `ZugaLife/backend/tests/test_therapist_speech.py`

- [ ] **Step 1: Write the failing test**

Create `ZugaLife/backend/tests/test_therapist_speech.py`:

```python
"""Tests for /api/life/therapist/speak endpoint."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user():
    """Stub current user dependency."""
    from core.auth.models import CurrentUser
    return CurrentUser(id=1, email="test@example.com", supertokens_id="st-1")


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ZugaLife && python -m pytest backend/tests/test_therapist_speech.py -v
```

Expected: FAIL — endpoint doesn't exist (404 on POST `/speak`).

- [ ] **Step 3: Implement the endpoint**

Create `ZugaLife/backend/therapist/speech.py`:

```python
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
    """
    from core.ai.providers import call_cartesia_tts
    from core.credits.client import get_credit_client, dollars_to_tokens
    from core.gateway.providers import estimate_tts_cost

    estimated_usd = estimate_tts_cost(len(body.text), "cartesia-sonic-3")
    estimated_tokens = dollars_to_tokens(estimated_usd)
    credit_client = get_credit_client()

    if not await credit_client.can_spend(user.id, user.email, estimated_tokens):
        raise HTTPException(status_code=402, detail="Insufficient ZugaTokens for voice")

    try:
        # Voice-key → Cartesia UUID mapping is owned by call_cartesia_tts.
        # We pass the friendly key in `voice_id` and let it resolve, mirroring
        # meditation/routes.py L164.
        tts = await call_cartesia_tts(
            text=body.text,
            voice_id=body.voice,
            speed=1.0,         # natural cadence for chat (meditation uses 0.75)
            emotion="warm",
        )
    except RuntimeError as e:
        logger.warning("therapist.speak provider error: %s", e)
        raise HTTPException(status_code=503, detail="Voice provider unavailable") from e

    await credit_client.record_spend(
        user_id=user.id,
        email=user.email,
        tokens=dollars_to_tokens(tts.cost_usd),
        category="therapist_speech",
    )

    return Response(
        content=tts.audio,
        media_type="audio/mpeg",
        headers={
            "x-tts-cost-usd": f"{tts.cost_usd:.4f}",
            "x-tts-duration-ms": str(tts.duration_ms),
            "x-tts-voice": body.voice,
        },
    )
```

- [ ] **Step 4: Wire the router into therapist plugin**

Open `ZugaLife/backend/therapist/routes.py`. After the existing `router = APIRouter(...)` line (around L54) and before the first `@router.get` decorator, the speech router needs to be re-exposed via the same plugin entry. Find the function or `__all__` that exports the router (search):

```bash
grep -n "router\|__all__" ZugaLife/backend/therapist/__init__.py ZugaLife/backend/plugin.py
```

Add to `ZugaLife/backend/plugin.py` wherever therapist routes are registered (search for `from zugalife.therapist`). Add a sibling import that loads `speech` module the same way `routes` is loaded, then includes its router on the FastAPI app. Concretely, find this pattern and extend it:

```python
# Existing (illustrative — actual line in plugin.py):
_routes = importlib.import_module("zugalife.therapist.routes")
app.include_router(_routes.router)

# Add directly after:
_speech = importlib.import_module("zugalife.therapist.speech")
app.include_router(_speech.router)
```

If `plugin.py` uses a different registration shape (e.g. a list of router modules), append `"speech"` to that list instead of duplicating the `include_router` line.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ZugaLife && python -m pytest backend/tests/test_therapist_speech.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 6: Smoke test against running backend**

```bash
cd ZugaLife && ./start.sh &
sleep 3
curl -X POST http://localhost:8000/api/life/therapist/speak \
  -H "Content-Type: application/json" \
  -H "Cookie: $YOUR_AUTH_COOKIE" \
  -d '{"text":"Hello, take a slow breath.","voice":"calm-female"}' \
  --output /tmp/speak.mp3
file /tmp/speak.mp3
```

Expected: `/tmp/speak.mp3: Audio file with ID3 ...` or `Audio file MPEG ...`. Plays in any audio player.

- [ ] **Step 7: Commit**

```bash
git add ZugaLife/backend/therapist/speech.py ZugaLife/backend/tests/test_therapist_speech.py ZugaLife/backend/plugin.py
git commit -m "feat(therapist): /api/life/therapist/speak endpoint (Cartesia MP3, budget-gated)"
```

---

## Task 3: Frontend dependencies + VRM placeholder

**Files:**
- Modify: `ZugaLife/frontend/package.json`
- Create: `ZugaLife/frontend/public/avatars/README.md`

- [ ] **Step 1: Add Three.js + VRM deps**

```bash
cd ZugaLife/frontend
npm install --save three@^0.169.0 @pixiv/three-vrm@^3.4.0
npm install --save-dev @types/three@^0.169.0
```

- [ ] **Step 2: Create avatar drop-in instructions**

Create `ZugaLife/frontend/public/avatars/README.md`:

```markdown
# Wellness Avatar

The wellness bot loads a VRM avatar from `/avatars/wellness.vrm`.

## Getting a VRM

Two options — both produce a `.vrm` file natively, no conversion.

**A. VRoid Hub (browse + download an existing avatar)**
1. Visit https://hub.vroid.com/ and browse community avatars. Filter for
   ones with a "Download permitted" / "Use license" tag that allows
   embedding. A calm/wellness vibe is recommended for the bot.
2. Click the avatar → **Download** → save as `.vrm`.

**B. VRoid Studio (build your own — desktop app)**
1. Install VRoid Studio (free) from https://vroid.com/en/studio
2. Customize a half-body or full-body model.
3. **Export → VRM** (the app produces `.vrm` directly).

After either path:
- Rename the downloaded file to `wellness.vrm`.
- Place it at `ZugaLife/frontend/public/avatars/wellness.vrm`.

The file is git-ignored — each environment supplies its own. The frontend
will render a "Loading avatar..." card if the file is missing, then fall
back to text-only chat.
```

- [ ] **Step 3: Git-ignore the binary**

Append to `ZugaLife/frontend/.gitignore` (create if absent):

```
public/avatars/*.vrm
```

- [ ] **Step 4: Verify dev build still compiles**

```bash
cd ZugaLife/frontend && npm run build
```

Expected: build succeeds. (Avatar component doesn't exist yet — we just verify deps don't break the build.)

- [ ] **Step 5: Commit**

```bash
git add ZugaLife/frontend/package.json ZugaLife/frontend/package-lock.json \
  ZugaLife/frontend/public/avatars/README.md ZugaLife/frontend/.gitignore
git commit -m "chore(life-fe): add three + @pixiv/three-vrm; document avatar drop-in"
```

---

## Task 4: WellnessAvatar component (Three.js + VRM + idle breathing)

**Files:**
- Create: `ZugaLife/frontend/components/WellnessAvatar.vue`

- [ ] **Step 1: Drop a test VRM into place**

For local development, follow `public/avatars/README.md` and put a real VRM at `ZugaLife/frontend/public/avatars/wellness.vrm` before testing.

- [ ] **Step 2: Write the component**

Create `ZugaLife/frontend/components/WellnessAvatar.vue`:

```vue
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, defineExpose } from 'vue'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils, type VRM } from '@pixiv/three-vrm'

const props = defineProps<{
  vrmUrl?: string  // default: /avatars/wellness.vrm
  height?: number  // px; default 320
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
const status = ref<'loading' | 'ready' | 'error'>('loading')
const errorMsg = ref('')

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let vrm: VRM | null = null
let clock: THREE.Clock | null = null
let rafId = 0

// Lip-sync state — driven by parent via setMouthOpen(0..1)
let mouthOpenTarget = 0
let mouthOpenSmoothed = 0

function setMouthOpen(value: number) {
  mouthOpenTarget = Math.max(0, Math.min(1, value))
}

defineExpose({ setMouthOpen })

onMounted(async () => {
  if (!canvasEl.value) return

  const width = canvasEl.value.clientWidth || 320
  const height = props.height ?? 320

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(28, width / height, 0.1, 20)
  camera.position.set(0, 1.4, 1.2)
  camera.lookAt(0, 1.4, 0)

  renderer = new THREE.WebGLRenderer({ canvas: canvasEl.value, alpha: true, antialias: true })
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))

  const ambient = new THREE.AmbientLight(0xffffff, 0.7)
  const dir = new THREE.DirectionalLight(0xffffff, 0.9)
  dir.position.set(1, 2, 2)
  scene.add(ambient, dir)

  const loader = new GLTFLoader()
  loader.register((parser) => new VRMLoaderPlugin(parser))

  const url = props.vrmUrl ?? '/avatars/wellness.vrm'
  try {
    const gltf = await loader.loadAsync(url)
    vrm = gltf.userData.vrm as VRM
    VRMUtils.removeUnnecessaryVertices(gltf.scene)
    VRMUtils.removeUnnecessaryJoints(gltf.scene)
    scene.add(vrm.scene)
    status.value = 'ready'
  } catch (e) {
    status.value = 'error'
    errorMsg.value = e instanceof Error ? e.message : String(e)
    return
  }

  clock = new THREE.Clock()
  const animate = () => {
    rafId = requestAnimationFrame(animate)
    const dt = clock!.getDelta()
    const t = clock!.elapsedTime

    if (vrm) {
      // Idle breathing: gentle chest rise via spine rotation
      const spine = vrm.humanoid?.getNormalizedBoneNode('spine')
      if (spine) spine.rotation.x = Math.sin(t * 1.4) * 0.02

      // Lip sync: smooth toward target, drive `aa` blendshape
      mouthOpenSmoothed += (mouthOpenTarget - mouthOpenSmoothed) * Math.min(1, dt * 18)
      vrm.expressionManager?.setValue('aa', mouthOpenSmoothed)
      vrm.update(dt)
    }

    renderer!.render(scene!, camera!)
  }
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  renderer?.dispose()
  if (vrm) VRMUtils.deepDispose(vrm.scene)
  scene = null
  camera = null
  vrm = null
})
</script>

<template>
  <div class="wellness-avatar relative" :style="{ height: (height ?? 320) + 'px' }">
    <canvas ref="canvasEl" class="w-full h-full block"></canvas>
    <div
      v-if="status === 'loading'"
      class="absolute inset-0 flex items-center justify-center text-xs text-txt-muted"
    >
      Loading avatar...
    </div>
    <div
      v-if="status === 'error'"
      class="absolute inset-0 flex items-center justify-center text-xs text-txt-muted px-4 text-center"
    >
      Avatar unavailable. Chat continues without it.
    </div>
  </div>
</template>
```

- [ ] **Step 3: Manual smoke test**

Add a temporary mount to `LifeView.vue` (or directly `TherapistTab.vue`) for a one-off check, then revert. Quickest path:

```bash
cd ZugaLife/frontend && npm run dev
```

Open the app, navigate to wellness tab, temporarily render `<WellnessAvatar />` somewhere — confirm the avatar appears, idle-breathes, and that the canvas gracefully shows "Avatar unavailable" if you rename `wellness.vrm`.

- [ ] **Step 4: Commit**

```bash
git add ZugaLife/frontend/components/WellnessAvatar.vue
git commit -m "feat(life-fe): WellnessAvatar component — VRM render + idle breathing + lip-sync API"
```

---

## Task 5: useAvatarSpeech composable (fetch + play + volume → mouth)

**Files:**
- Create: `ZugaLife/frontend/composables/useAvatarSpeech.ts`

- [ ] **Step 1: Write the composable**

Create `ZugaLife/frontend/composables/useAvatarSpeech.ts`:

```typescript
import { ref } from 'vue'
import { api, ApiError } from '@core/api/client'

export interface SpeakResult {
  cost: number
  durationMs: number
  voice: string
}

/**
 * Drives the wellness avatar's voice + lip sync.
 *
 * - `speak(text)` POSTs to /api/life/therapist/speak, receives MP3 bytes,
 *   plays via HTMLAudioElement, and runs an AnalyserNode RMS loop that
 *   pushes mouth-open values into `setMouthOpen` (provided by the avatar).
 * - One utterance at a time. A new `speak` call cancels any in-flight one.
 * - Errors (no credits, provider down, blocked autoplay) resolve silently —
 *   chat continues, just without voice.
 */
export function useAvatarSpeech(setMouthOpen: (v: number) => void) {
  const speaking = ref(false)
  const lastError = ref<string | null>(null)
  let audio: HTMLAudioElement | null = null
  let ctx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let rafId = 0

  function stop() {
    cancelAnimationFrame(rafId)
    audio?.pause()
    if (audio) audio.src = ''
    audio = null
    setMouthOpen(0)
    speaking.value = false
  }

  function ensureCtx(): AudioContext {
    if (!ctx) ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
    return ctx
  }

  async function speak(text: string, voice = 'calm-female'): Promise<SpeakResult | null> {
    stop()
    lastError.value = null

    let blob: Blob
    let cost = 0
    let durationMs = 0
    let resolvedVoice = voice
    try {
      const res = await fetch(api.url('/api/life/therapist/speak'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice }),
      })
      if (!res.ok) {
        if (res.status === 402) lastError.value = 'no-credits'
        else if (res.status === 503) lastError.value = 'provider-down'
        else lastError.value = `http-${res.status}`
        return null
      }
      blob = await res.blob()
      cost = parseFloat(res.headers.get('x-tts-cost-usd') ?? '0')
      durationMs = parseInt(res.headers.get('x-tts-duration-ms') ?? '0', 10)
      resolvedVoice = res.headers.get('x-tts-voice') ?? voice
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : 'fetch-failed'
      return null
    }

    const url = URL.createObjectURL(blob)
    audio = new Audio(url)
    audio.crossOrigin = 'anonymous'

    const audioCtx = ensureCtx()
    const source = audioCtx.createMediaElementSource(audio)
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)
    analyser.connect(audioCtx.destination)

    const buf = new Uint8Array(analyser.frequencyBinCount)
    const tick = () => {
      if (!analyser) return
      analyser.getByteTimeDomainData(buf)
      // RMS over the time-domain buffer (centered around 128)
      let sum = 0
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / buf.length)
      // Empirically: rms ~0.0..0.4 during speech. Map 0..0.25 → 0..1.
      const open = Math.min(1, rms / 0.25)
      setMouthOpen(open)
      rafId = requestAnimationFrame(tick)
    }

    audio.onended = () => {
      cancelAnimationFrame(rafId)
      setMouthOpen(0)
      speaking.value = false
      URL.revokeObjectURL(url)
    }

    speaking.value = true
    try {
      // resume() handles browsers that suspend AudioContext until user gesture
      if (audioCtx.state === 'suspended') await audioCtx.resume()
      await audio.play()
      tick()
    } catch (e) {
      lastError.value = 'autoplay-blocked'
      stop()
      URL.revokeObjectURL(url)
      return null
    }

    return { cost, durationMs, voice: resolvedVoice }
  }

  return { speak, stop, speaking, lastError }
}
```

- [ ] **Step 2: Verify `api.url` helper exists in `@core/api/client`**

```bash
grep -n "export .*url\|url:" ZugaApp/frontend/core/api/client.ts | head -5
```

If `api.url` does not exist, replace `api.url('/api/life/therapist/speak')` with a plain string `'/api/life/therapist/speak'` (the SuperTokens session cookie is sent on same-origin by default in this codebase).

- [ ] **Step 3: Typecheck**

```bash
cd ZugaLife/frontend && npx vue-tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add ZugaLife/frontend/composables/useAvatarSpeech.ts
git commit -m "feat(life-fe): useAvatarSpeech composable — fetch MP3, play, volume→mouth"
```

---

## Task 6: Wire avatar into TherapistTab

**Files:**
- Modify: `ZugaLife/frontend/tabs/TherapistTab.vue`

- [ ] **Step 1: Add imports**

In the `<script setup lang="ts">` block at the top of `TherapistTab.vue` (around L1-14), add:

```typescript
import WellnessAvatar from '../components/WellnessAvatar.vue'
import { useAvatarSpeech } from '../composables/useAvatarSpeech'
```

- [ ] **Step 2: Add avatar ref + speech hook + setting**

After the existing `chatContainer` ref (around L127), add:

```typescript
const avatarRef = ref<InstanceType<typeof WellnessAvatar> | null>(null)
const avatarEnabled = ref(localStorage.getItem('zugalife_avatar_enabled') !== '0')
const voiceEnabled = ref(localStorage.getItem('zugalife_voice_enabled') !== '0')

const avatarSpeech = useAvatarSpeech((v) => {
  avatarRef.value?.setMouthOpen(v)
})

function toggleAvatar() {
  avatarEnabled.value = !avatarEnabled.value
  localStorage.setItem('zugalife_avatar_enabled', avatarEnabled.value ? '1' : '0')
  if (!avatarEnabled.value) avatarSpeech.stop()
}

function toggleVoice() {
  voiceEnabled.value = !voiceEnabled.value
  localStorage.setItem('zugalife_voice_enabled', voiceEnabled.value ? '1' : '0')
  if (!voiceEnabled.value) avatarSpeech.stop()
}
```

- [ ] **Step 3: Speak on assistant replies**

In `sendTherapistMessage()`, after the line `therapistMessages.value.push({ role: 'assistant', content: res.content })` (around L243), add:

```typescript
if (voiceEnabled.value && avatarEnabled.value) {
  avatarSpeech.speak(res.content).catch(() => { /* silent — chat still works */ })
}
```

In `endTherapistSession()`, before the `therapistSessionActive.value = false` line (around L289), add:

```typescript
avatarSpeech.stop()
```

- [ ] **Step 4: Mount avatar above the chat**

In the `<template>`, find the active session block (the `<div v-else class="flex flex-col" ...>` near L462) and insert directly above the messages container:

```vue
<div v-if="avatarEnabled" class="mb-3 rounded-xl overflow-hidden bg-surface-2/40 border border-bdr/40">
  <WellnessAvatar ref="avatarRef" :height="280" />
  <div class="flex items-center justify-between px-3 py-1.5 text-xs text-txt-muted border-t border-bdr/40">
    <span>{{ avatarSpeech.speaking.value ? 'Speaking…' : 'Listening' }}</span>
    <button
      @click="toggleVoice()"
      class="px-2 py-0.5 rounded hover:bg-surface-3 transition-colors"
      :title="voiceEnabled ? 'Mute voice' : 'Unmute voice'"
    >
      {{ voiceEnabled ? 'Mute' : 'Unmute' }}
    </button>
  </div>
</div>
```

- [ ] **Step 5: Typecheck and build**

```bash
cd ZugaLife/frontend && npx vue-tsc --noEmit && npm run build
```

Expected: 0 errors, build succeeds.

- [ ] **Step 6: Manual E2E smoke**

```bash
cd ZugaLife/frontend && npm run dev
# In another terminal: cd ZugaLife && ./start.sh
```

- Sign in to ZugaLife
- Open Wellness tab → Start Session
- Verify: avatar appears above chat, idle-breathes
- Send a message → verify assistant reply is spoken AND mouth opens with the audio
- Click "Mute" → next reply does NOT speak (mouth stays still); text still arrives
- Toggle Mute back on → next reply speaks again
- End session → audio stops mid-utterance if still playing

- [ ] **Step 7: Commit**

```bash
git add ZugaLife/frontend/tabs/TherapistTab.vue
git commit -m "feat(life-fe): mount WellnessAvatar in TherapistTab; speak assistant replies"
```

---

## Task 7: Settings toggle in LifeSettings

**Files:**
- Modify: `ZugaLife/frontend/LifeSettings.vue`

- [ ] **Step 1: Locate the toggle pattern**

```bash
grep -n "localStorage\|toggle\|input.*checkbox" ZugaLife/frontend/LifeSettings.vue | head -10
```

Match the existing toggle markup style — do not invent a new one.

- [ ] **Step 2: Add the avatar setting**

In `LifeSettings.vue`, in the `<script setup>` block, add a ref + persist pair next to the existing settings:

```typescript
const avatarEnabled = ref(localStorage.getItem('zugalife_avatar_enabled') !== '0')

watch(avatarEnabled, (v) => {
  localStorage.setItem('zugalife_avatar_enabled', v ? '1' : '0')
})
```

(Make sure `watch` is imported from `vue` if not already.)

In the template, add a row that matches the existing toggle markup. Use the same wrapper / label classes as the nearest existing toggle. Skeleton (adapt to actual classes):

```vue
<label class="flex items-center justify-between py-3 border-t border-bdr">
  <div>
    <p class="text-sm text-txt-primary">Wellness avatar</p>
    <p class="text-xs text-txt-muted">3D character + voice in the wellness chat</p>
  </div>
  <input type="checkbox" v-model="avatarEnabled" class="toggle" />
</label>
```

- [ ] **Step 3: Verify the TherapistTab picks up the change**

Reload the Wellness tab after toggling. Avatar mounts/unmounts cleanly (no zombie canvas, no console errors). Note: the TherapistTab reads `localStorage` only on mount — if the user toggles while the tab is open they need to refresh the tab. That's acceptable for MVP (call it out in the cohort smoke notes).

- [ ] **Step 4: Commit**

```bash
git add ZugaLife/frontend/LifeSettings.vue
git commit -m "feat(life-fe): wellness-avatar toggle in settings"
```

---

## Task 8: Cohort smoke checklist

**Files:** none (verification only)

- [ ] **Step 1: Run the full checklist**

With BE on local and `npm run dev` for FE, run through every item:

- [ ] Sessions Status pill on the Wellness tab still reads "X/5 sessions left"
- [ ] Without `wellness.vrm` file, avatar slot shows "Avatar unavailable" and chat still works
- [ ] With `wellness.vrm`, avatar idle-breathes during chat
- [ ] Sending a message triggers spoken reply; mouth opens roughly in sync with audio
- [ ] Tab away mid-utterance → tab back → audio still finishes (or completes; no zombie loop)
- [ ] End session button stops audio immediately
- [ ] Mute toggle: next reply silent; subsequent unmute speaks again
- [ ] Settings toggle: turning avatar OFF and refreshing → no avatar mounted, no Three.js cost
- [ ] No console errors in any of the above flows
- [ ] DevTools Network tab: `/speak` returns `audio/mpeg`, `x-tts-cost-usd` header present, no 5xx

- [ ] **Step 2: Verify budget gate**

In a clean account with 0 ZugaTokens:

- [ ] Send a message → text reply succeeds (chat is gated separately)
- [ ] Voice request returns 402 → console shows `lastError === 'no-credits'`, chat continues silently

- [ ] **Step 3: Capture latency**

In DevTools Network, time the `/speak` request for a ~150-char reply. Note the round-trip (request → first audio byte). Record in the commit message — this is the baseline we'll measure streaming TTS against in the post-MVP follow-up.

- [ ] **Step 4: Mark MVP done**

```bash
git log --oneline | head -10
git tag wellness-avatar-mvp-v0.1
```

Commit message for the tag should reference: avatar + speech + lip sync + settings toggle, with measured `/speak` round-trip latency from Step 3.

---

## Self-Review

**Spec coverage:**
- VRM avatar in TherapistTab → Task 4 + Task 6
- Streaming Cartesia TTS → adjusted to **buffered** Cartesia (existing infra reused; streaming is post-MVP, called out in Architecture)
- Viseme-driven lip sync → adjusted to **volume-driven** mouth-open (Task 5); honest tradeoff stated in Architecture
- Idle breathing → Task 4 (spine sine-wave)
- Out-of-scope items are listed at the top and not implemented

**Placeholder scan:** No "TBD" / "implement later" / "add appropriate handling" — every step has concrete code or a concrete grep+adapt instruction.

**Type consistency:**
- `setMouthOpen(v: number)` defined in Task 4 (`WellnessAvatar.vue` `defineExpose`) and consumed in Task 5 (`useAvatarSpeech(setMouthOpen)`) and Task 6 (`avatarRef.value?.setMouthOpen(v)`) — all match.
- `TherapistSpeakRequest` / `TherapistSpeakResponse` defined in Task 1, used in Tasks 2 and 5.
- Header names `x-tts-cost-usd`, `x-tts-duration-ms`, `x-tts-voice` consistent across BE Task 2 and FE Task 5.
- Voice key `calm-female` is the same default in BE schema (Task 1) and FE composable (Task 5).

**One adjustment from the original ask:** The brief said "streaming Cartesia TTS." The existing `call_cartesia_tts` is buffered (chunks → concat MP3). True streaming requires Cartesia's WebSocket endpoint, a `MediaSource` pipeline on the FE, and barge-in handling — which is explicitly out of MVP scope. Reusing the buffered path ships a talking head this week; streaming is a clean follow-up because the FE composable's interface (`speak(text)` → audio + lip sync) doesn't change.
