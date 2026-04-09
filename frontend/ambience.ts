/**
 * Ambient sound player for meditation.
 * Uses dual-track crossfade looping to eliminate audible loop points.
 * Two Audio elements alternate — as one approaches its end, the other
 * fades in from the start, creating a seamless continuous ambience.
 */

type AmbienceType = 'rain' | 'ocean' | 'forest' | 'bowls'

let trackA: HTMLAudioElement | null = null
let trackB: HTMLAudioElement | null = null
let activeTrack: 'A' | 'B' = 'A'
let crossfadeTimer: ReturnType<typeof setInterval> | null = null
let targetVolume = 0.4
const CROSSFADE_DURATION = 4 // seconds of overlap

const AMBIENCE_FILES: Record<AmbienceType, string> = {
  rain: '/ambience/rain.mp3',
  ocean: '/ambience/ocean.mp3',
  forest: '/ambience/forest.mp3',
  bowls: '/ambience/bowls.mp3',
}

function createTrack(src: string, volume: number): HTMLAudioElement {
  const el = new Audio(src)
  el.volume = volume
  el.preload = 'auto'
  return el
}

function startCrossfadeLoop(): void {
  if (crossfadeTimer) clearInterval(crossfadeTimer)

  crossfadeTimer = setInterval(() => {
    const current = activeTrack === 'A' ? trackA : trackB
    const next = activeTrack === 'A' ? trackB : trackA
    if (!current || !next) return

    const remaining = current.duration - current.currentTime
    if (isNaN(remaining) || remaining > CROSSFADE_DURATION) return

    // Start crossfade — bring in the next track
    next.currentTime = 0
    next.volume = 0
    next.play().catch(() => {})

    // Fade over CROSSFADE_DURATION
    const steps = 20
    const stepTime = (CROSSFADE_DURATION * 1000) / steps
    let step = 0
    const fadeInterval = setInterval(() => {
      step++
      const progress = step / steps
      if (next) next.volume = progress * targetVolume
      if (current) current.volume = (1 - progress) * targetVolume
      if (step >= steps) {
        clearInterval(fadeInterval)
        current.pause()
        current.currentTime = 0
        activeTrack = activeTrack === 'A' ? 'B' : 'A'
      }
    }, stepTime)
  }, 500)
}

export function startAmbience(type: AmbienceType, volume: number): void {
  stopAmbience()
  targetVolume = volume

  const src = AMBIENCE_FILES[type]
  trackA = createTrack(src, volume)
  trackB = createTrack(src, 0)
  activeTrack = 'A'

  trackA.play().catch(() => { /* autoplay blocked — voice play() covers the gesture */ })
  startCrossfadeLoop()
}

export function setAmbienceVolume(volume: number): void {
  targetVolume = volume
  const current = activeTrack === 'A' ? trackA : trackB
  if (current && !current.paused) current.volume = volume
}

export function pauseAmbience(): void {
  if (crossfadeTimer) { clearInterval(crossfadeTimer); crossfadeTimer = null }
  trackA?.pause()
  trackB?.pause()
}

export function resumeAmbience(): void {
  const current = activeTrack === 'A' ? trackA : trackB
  if (current) {
    current.volume = targetVolume
    current.play().catch(() => {})
  }
  startCrossfadeLoop()
}

export function stopAmbience(): void {
  if (crossfadeTimer) { clearInterval(crossfadeTimer); crossfadeTimer = null }
  if (trackA) { trackA.pause(); trackA.src = ''; trackA = null }
  if (trackB) { trackB.pause(); trackB.src = ''; trackB = null }
}
