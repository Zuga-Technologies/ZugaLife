import { ref } from 'vue'
import { getToken } from '@core/api/client'

export interface SpeakResult {
  cost: number
  durationMs: number
  voice: string
}

/**
 * Drives the wellness avatar's voice + lip sync.
 *
 * One utterance at a time — a new `speak` call cancels any in-flight one.
 * Errors (no credits, provider down, blocked autoplay) resolve silently —
 * chat continues, just without voice.
 */
export function useAvatarSpeech(setMouthOpen: (v: number) => void) {
  const speaking = ref(false)
  const lastError = ref<string | null>(null)
  let audio: HTMLAudioElement | null = null
  let ctx: AudioContext | null = null
  let source: MediaElementAudioSourceNode | null = null
  let analyser: AnalyserNode | null = null
  let rafId = 0
  let currentObjectUrl: string | null = null

  function stop() {
    cancelAnimationFrame(rafId)
    audio?.pause()
    if (audio) audio.src = ''
    audio = null
    source?.disconnect()
    source = null
    analyser?.disconnect()
    analyser = null
    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl)
      currentObjectUrl = null
    }
    setMouthOpen(0)
    speaking.value = false
  }

  function ensureCtx(): AudioContext {
    if (!ctx)
      ctx = new (
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      )()
    return ctx
  }

  /**
   * Create+resume the AudioContext during a known user gesture (Start Session,
   * first Send, etc). Browsers suspend AudioContext until a gesture, and that
   * resume can add ~100ms to the first utterance — paying it up-front means the
   * first reply plays as soon as the audio bytes land.
   */
  async function prewarm(): Promise<void> {
    const c = ensureCtx()
    if (c.state === 'suspended') {
      try { await c.resume() } catch { /* swallow — we'll retry inside speak() */ }
    }
  }

  async function speak(text: string, voice = ''): Promise<SpeakResult | null> {
    stop()
    lastError.value = null

    let blob: Blob
    let cost = 0
    const durationMs = 0
    let resolvedVoice = voice
    try {
      // Auth: ZugaApp uses Bearer-token-from-localStorage, not cookies.
      // Match @core/api/client so we don't 401.
      const token = getToken()
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch('/api/life/therapist/speak', {
        method: 'POST',
        headers,
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
      resolvedVoice = res.headers.get('x-tts-voice') ?? voice
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : 'fetch-failed'
      return null
    }

    currentObjectUrl = URL.createObjectURL(blob)
    audio = new Audio(currentObjectUrl)
    audio.crossOrigin = 'anonymous'

    const audioCtx = ensureCtx()
    source = audioCtx.createMediaElementSource(audio)
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)
    analyser.connect(audioCtx.destination)

    const buf = new Uint8Array(analyser.frequencyBinCount)
    const tick = () => {
      if (!analyser) return
      analyser.getByteTimeDomainData(buf)
      // RMS over time-domain (centered around 128). rms ~0..0.4 during speech.
      let sum = 0
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / buf.length)
      const open = Math.min(1, rms / 0.25)
      setMouthOpen(open)
      rafId = requestAnimationFrame(tick)
    }

    audio.onended = () => {
      cancelAnimationFrame(rafId)
      setMouthOpen(0)
      speaking.value = false
      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl)
        currentObjectUrl = null
      }
    }

    speaking.value = true
    try {
      // resume() handles browsers that suspend AudioContext until user gesture
      if (audioCtx.state === 'suspended') await audioCtx.resume()
      await audio.play()
      tick()
    } catch (_e) {
      lastError.value = 'autoplay-blocked'
      stop()
      return null
    }

    return { cost, durationMs, voice: resolvedVoice }
  }

  return { speak, stop, prewarm, speaking, lastError }
}
