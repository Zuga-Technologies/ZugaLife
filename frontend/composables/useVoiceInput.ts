import { ref } from 'vue'
import { getToken } from '@core/api/client'

/**
 * Browser MediaRecorder wrapper for Whisper-bound voice input.
 *
 * - `start()` requests mic permission, begins recording.
 * - `stop()` halts recording and resolves with a Blob (audio/webm or
 *   whatever the browser produces; the BE accepts any audio/* type).
 * - One recording at a time. Calling start() while recording is a no-op.
 * - Errors (permission denied, no mic) surface via `lastError` ref —
 *   callers can show a "Mic blocked, type instead" prompt.
 *
 * Browser support:
 *   ✓ Chrome / Edge desktop, Chrome Android — webm/opus
 *   ✓ Firefox — ogg/opus
 *   ✓ iOS Safari 14.3+ — mp4/aac (different mime, BE handles it)
 *   ✗ Older Safari < 14.3 — MediaRecorder unsupported, isSupported = false
 */
export function useVoiceInput() {
  const recording = ref(false)
  const lastError = ref<string | null>(null)

  let mediaRecorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: Blob[] = []
  let stopResolve: ((blob: Blob | null) => void) | null = null

  const isSupported = typeof window !== 'undefined'
    && 'MediaRecorder' in window
    && !!navigator.mediaDevices?.getUserMedia

  async function start(): Promise<boolean> {
    if (recording.value) return false
    lastError.value = null

    if (!isSupported) {
      lastError.value = 'unsupported'
      return false
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      // Most common: NotAllowedError (user denied permission), NotFoundError
      // (no mic). Either way we stop here — caller renders a fallback.
      lastError.value = e instanceof Error ? e.name : 'getUserMedia-failed'
      return false
    }

    chunks = []
    try {
      // Let the browser pick its preferred codec — webm/opus on Chromium,
      // mp4/aac on iOS, ogg/opus on Firefox. Whisper accepts all of these.
      mediaRecorder = new MediaRecorder(stream)
    } catch (e) {
      lastError.value = e instanceof Error ? e.name : 'mediarecorder-failed'
      stream.getTracks().forEach(t => t.stop())
      stream = null
      return false
    }

    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunks.push(ev.data)
    }
    mediaRecorder.onstop = () => {
      const mime = mediaRecorder?.mimeType || 'audio/webm'
      const blob = chunks.length > 0 ? new Blob(chunks, { type: mime }) : null
      stream?.getTracks().forEach(t => t.stop())
      stream = null
      mediaRecorder = null
      recording.value = false
      stopResolve?.(blob)
      stopResolve = null
    }

    mediaRecorder.start()
    recording.value = true
    return true
  }

  function stop(): Promise<Blob | null> {
    if (!recording.value || !mediaRecorder) {
      return Promise.resolve(null)
    }
    return new Promise<Blob | null>((resolve) => {
      stopResolve = resolve
      mediaRecorder?.stop()
    })
  }

  function cancel() {
    if (!mediaRecorder) return
    chunks = []
    try { mediaRecorder.stop() } catch { /* ignore */ }
    stream?.getTracks().forEach(t => t.stop())
    stream = null
    mediaRecorder = null
    recording.value = false
    stopResolve?.(null)
    stopResolve = null
  }

  return { recording, lastError, isSupported, start, stop, cancel }
}


export interface TranscribeResult {
  text: string
  durationSec: number
  costUsd: number
}

/**
 * POST a recorded audio blob to the BE and resolve with the transcript.
 * Returns null on any error; callers should check lastError on the recorder
 * AND the returned value.
 *
 * Errors:
 *   402 → no-credits (caller should surface the standard insufficient-token UI)
 *   413 → recording-too-long (>25 MB)
 *   503 → provider-down (caller should fall back to text input silently)
 */
export async function transcribeBlob(blob: Blob): Promise<{ result: TranscribeResult | null; error: string | null }> {
  const form = new FormData()
  // The filename hint helps OpenAI sniff the format if content-type is missing.
  const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'
  form.append('audio', blob, `voice-input.${ext}`)

  let res: Response
  try {
    // Auth: ZugaApp uses Bearer-token-from-localStorage, not cookies — match
    // the api client (`@core/api/client`) so we don't 401. Don't set
    // Content-Type; the browser must add the multipart boundary itself.
    const token = getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    res = await fetch('/api/life/therapist/transcribe', {
      method: 'POST',
      headers,
      body: form,
    })
  } catch (e) {
    return { result: null, error: e instanceof Error ? e.message : 'fetch-failed' }
  }

  if (!res.ok) {
    if (res.status === 402) return { result: null, error: 'no-credits' }
    if (res.status === 413) return { result: null, error: 'too-large' }
    if (res.status === 503) return { result: null, error: 'provider-down' }
    return { result: null, error: `http-${res.status}` }
  }

  try {
    const json = await res.json() as { text: string; duration_sec: number; cost_usd: number }
    return {
      result: { text: json.text, durationSec: json.duration_sec, costUsd: json.cost_usd },
      error: null,
    }
  } catch (e) {
    return { result: null, error: e instanceof Error ? e.message : 'parse-failed' }
  }
}
