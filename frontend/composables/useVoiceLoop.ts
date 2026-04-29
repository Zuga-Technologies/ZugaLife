import { ref, onBeforeUnmount } from 'vue'
import { transcribeBlob } from './useVoiceInput'

/**
 * Continuous voice loop — the "unmute and just talk" pattern.
 *
 * Pattern lifted from ZugaGamerOverlay's voice service (src/services/voice.ts):
 * client-side VAD via AnalyserNode RMS + silence-timeout segmentation. When
 * silence persists for SILENCE_MS after the user has been speaking, the
 * MediaRecorder stops, the blob goes to Whisper, and the resulting text is
 * handed back to the caller so the wellness chat can auto-send it.
 *
 * UX contract:
 *   - muted=true: mic is fully off (no stream, no recorder, no analyser).
 *     This is the calm default — privacy + power.
 *   - muted=false: mic is live, the loop is actively segmenting utterances.
 *
 * Differences vs the gamer overlay:
 *   - No wake word — wellness chat is intentional, not ambient.
 *   - Whisper-on-blob, not streaming STT (cost + simplicity).
 *   - Listening is paused while the avatar is speaking (no echo bleed).
 */

export type VoicePhase =
  | 'idle'        // muted, nothing running
  | 'listening'   // mic open, waiting for the user to say something
  | 'capturing'   // user is currently speaking, MediaRecorder is recording
  | 'transcribing' // utterance handed to Whisper
  | 'paused'      // muted-by-output (avatar speaking)

interface UseVoiceLoopOptions {
  onTranscript: (text: string) => Promise<void> | void
  isOutputSpeaking: () => boolean
  // Configurable for future tuning. Defaults are empirically tuned for a
  // medium-quiet room with normal speech volume.
  vadThreshold?: number      // RMS at which we count a frame as speech
  silenceMs?: number          // ms of silence after speech before we end an utterance
  maxUtteranceMs?: number     // hard cap so a held button or hum can't run forever
  voiceFramesRequired?: number // consecutive frames above threshold before we trust it's voice
}

// Web Speech API — non-standard, ambient-typed below so TS doesn't whine.
// We use it purely for live captions (interim results while the user is
// speaking). The canonical transcript still comes from Whisper-on-blob.
type SR = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean; length: number }> }) => void) | null
  onerror: ((e: unknown) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type SRCtor = new () => SR
function getSpeechRecognitionCtor(): SRCtor | null {
  const w = window as unknown as { SpeechRecognition?: SRCtor; webkitSpeechRecognition?: SRCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function useVoiceLoop(opts: UseVoiceLoopOptions) {
  const muted = ref(true)
  const phase = ref<VoicePhase>('idle')
  const volume = ref(0)
  const lastError = ref<string | null>(null)
  // Live caption: in-progress recognition text. Empty when nothing is being
  // heard. Updates frame-by-frame as the user speaks; cleared once the
  // utterance is finalised and handed off to Whisper.
  const interimTranscript = ref('')

  const VAD_THRESHOLD = opts.vadThreshold ?? 0.025
  const SILENCE_MS = opts.silenceMs ?? 1300
  const MAX_UTTERANCE_MS = opts.maxUtteranceMs ?? 30_000
  const VOICE_FRAMES_REQ = opts.voiceFramesRequired ?? 3

  let stream: MediaStream | null = null
  let ctx: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let recorder: MediaRecorder | null = null
  let chunks: Blob[] = []
  let rafId = 0
  let smoothedVol = 0
  let voiceFrames = 0
  let silenceTimer: ReturnType<typeof setTimeout> | null = null
  let utteranceStartedAt = 0
  let utteranceCapAt = 0
  let speaking = false
  let recognition: SR | null = null
  // Chrome's SpeechRecognition stops itself after a few seconds of silence
  // even with continuous=true. We restart it from `onend` while the loop is
  // still unmuted so captions resume on the next utterance.
  let recognitionRestartPending = false

  function clearSilenceTimer() {
    if (silenceTimer) {
      clearTimeout(silenceTimer)
      silenceTimer = null
    }
  }

  async function unmute(): Promise<boolean> {
    if (!muted.value) return true
    lastError.value = null

    if (!navigator.mediaDevices?.getUserMedia) {
      lastError.value = 'unsupported'
      return false
    }

    // Some browsers (older Safari, some Android WebViews) reject the rich
    // constraint object with OverconstrainedError. Fall back to bare
    // `audio: true` so the mic still works without DSP niceties.
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (e) {
      const name = e instanceof Error ? e.name : ''
      if (name === 'OverconstrainedError' || name === 'NotReadableError' || name === 'TypeError') {
        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        } catch (e2) {
          lastError.value = e2 instanceof Error ? e2.name : 'getUserMedia-failed'
          console.warn('[voice-loop] getUserMedia (fallback) failed:', e2)
          return false
        }
      } else {
        lastError.value = name || 'getUserMedia-failed'
        console.warn('[voice-loop] getUserMedia failed:', e)
        return false
      }
    }

    try {
      const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctx = new Ctor()
      // Safari / iOS create AudioContexts in the 'suspended' state and the
      // analyser returns silent buffers until resume() runs inside the same
      // user-gesture chain. Without this, unmute appears to "succeed" but
      // the volume meter never moves and no utterance is ever segmented.
      if (ctx.state === 'suspended') {
        try { await ctx.resume() } catch { /* best-effort */ }
      }
      const src = ctx.createMediaStreamSource(stream)
      analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      src.connect(analyser)

      recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data)
      }
      recorder.onstop = handleUtteranceComplete
    } catch (e) {
      lastError.value = e instanceof Error ? e.name : 'audio-init-failed'
      console.warn('[voice-loop] audio init failed:', e)
      teardownAudio()
      return false
    }

    startRecognition()

    muted.value = false
    phase.value = 'listening'
    smoothedVol = 0
    voiceFrames = 0
    speaking = false
    monitorTick()
    return true
  }

  function startRecognition() {
    const Ctor = getSpeechRecognitionCtor()
    if (!Ctor) return // Safari/iOS: no Web Speech API. Captions silently disabled.
    try {
      const r = new Ctor()
      r.continuous = true
      r.interimResults = true
      r.lang = 'en-US'
      r.onresult = (e) => {
        let finalText = ''
        let interim = ''
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i]
          const text = res[0].transcript
          if (res.isFinal) finalText += text
          else interim += text
        }
        // Whichever is freshest wins as the caption. We don't keep finals
        // around — Whisper is the canonical source — so the caption clears
        // naturally when the user finishes speaking.
        interimTranscript.value = (finalText + interim).trim()
      }
      r.onerror = (e) => {
        // 'no-speech' / 'aborted' are routine; just let onend restart us.
        console.warn('[voice-loop] SpeechRecognition error', e)
      }
      r.onend = () => {
        if (!muted.value && !recognitionRestartPending) {
          recognitionRestartPending = true
          setTimeout(() => {
            recognitionRestartPending = false
            if (!muted.value && recognition) {
              try { recognition.start() } catch { /* already running */ }
            }
          }, 250)
        }
      }
      recognition = r
      r.start()
    } catch (e) {
      console.warn('[voice-loop] SpeechRecognition init failed:', e)
      recognition = null
    }
  }

  function stopRecognition() {
    if (!recognition) return
    try { recognition.abort() } catch { /* ignore */ }
    recognition.onresult = null
    recognition.onerror = null
    recognition.onend = null
    recognition = null
    interimTranscript.value = ''
  }

  function mute() {
    if (muted.value) return
    muted.value = true
    clearSilenceTimer()
    cancelAnimationFrame(rafId)
    if (recorder?.state === 'recording') {
      // Drop the in-flight chunk — user explicitly muted, don't send.
      chunks = []
      try { recorder.stop() } catch { /* ignore */ }
    }
    stopRecognition()
    teardownAudio()
    phase.value = 'idle'
    volume.value = 0
    speaking = false
  }

  function teardownAudio() {
    stream?.getTracks().forEach(t => t.stop())
    try { ctx?.close() } catch { /* ignore */ }
    stream = null
    ctx = null
    analyser = null
    recorder = null
  }

  function monitorTick() {
    if (!analyser || muted.value) return
    rafId = requestAnimationFrame(monitorTick)

    const buf = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / buf.length)
    // Light EMA — fast enough to track speech, smoothed enough that single
    // loud frames (mouse click, keyboard) don't false-trigger.
    smoothedVol += (rms - smoothedVol) * 0.3
    volume.value = Math.min(1, smoothedVol / 0.15)

    // Echo guard: while the avatar is speaking, pause segmentation. Without
    // this, TTS bleed through the mic gets picked up as user speech and
    // creates a feedback loop.
    if (opts.isOutputSpeaking()) {
      phase.value = 'paused'
      voiceFrames = 0
      clearSilenceTimer()
      // Don't capture or stop here; just wait it out.
      return
    }

    if (phase.value === 'transcribing') return

    if (phase.value === 'paused') phase.value = 'listening'

    if (smoothedVol > VAD_THRESHOLD) {
      voiceFrames++
      clearSilenceTimer()

      // Voice has crossed the trust threshold and we're not already
      // capturing — open a fresh utterance.
      if (voiceFrames >= VOICE_FRAMES_REQ && !speaking) {
        speaking = true
        chunks = []
        utteranceStartedAt = Date.now()
        utteranceCapAt = utteranceStartedAt + MAX_UTTERANCE_MS
        try {
          recorder?.start()
          phase.value = 'capturing'
        } catch (e) {
          lastError.value = e instanceof Error ? e.name : 'recorder-start-failed'
          speaking = false
        }
      }

      // Hard cap — a hum / continuous noise can't run forever.
      if (speaking && Date.now() > utteranceCapAt) {
        finishUtterance('max-utterance')
      }
    } else {
      voiceFrames = Math.max(0, voiceFrames - 1)
      if (speaking && !silenceTimer) {
        silenceTimer = setTimeout(() => finishUtterance('silence'), SILENCE_MS)
      }
    }
  }

  function finishUtterance(_reason: 'silence' | 'max-utterance') {
    clearSilenceTimer()
    if (recorder?.state === 'recording') {
      try { recorder.stop() } catch { /* ignore */ }
    }
  }

  async function handleUtteranceComplete() {
    speaking = false
    const utteranceMs = Date.now() - utteranceStartedAt
    if (chunks.length === 0 || muted.value) {
      chunks = []
      return
    }

    const mime = recorder?.mimeType || 'audio/webm'
    const blob = new Blob(chunks, { type: mime })
    chunks = []

    // Filter junk: anything < 400ms is almost certainly cough/click/noise.
    if (utteranceMs < 400 || blob.size < 1500) {
      phase.value = muted.value ? 'idle' : 'listening'
      return
    }

    phase.value = 'transcribing'
    try {
      const { result, error } = await transcribeBlob(blob)
      if (result?.text?.trim()) {
        await opts.onTranscript(result.text.trim())
      } else if (error) {
        lastError.value = error
      }
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : 'transcribe-failed'
    } finally {
      // Caption was the in-flight live preview; the canonical text is now
      // committed (or sent), so wipe it before the next utterance starts.
      interimTranscript.value = ''
      phase.value = muted.value ? 'idle' : 'listening'
    }
  }

  async function toggle() {
    if (muted.value) await unmute()
    else mute()
  }

  onBeforeUnmount(() => mute())

  return { muted, phase, volume, lastError, interimTranscript, toggle, unmute, mute }
}
