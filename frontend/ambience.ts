/**
 * Ambient sound player for meditation.
 * Plays real MP3 recordings (rain, ocean, forest, bowls) from /ambience/*.mp3.
 * Keeps the same export API so LifeView.vue doesn't need changes.
 */

type AmbienceType = 'rain' | 'ocean' | 'forest' | 'bowls'

let audioEl: HTMLAudioElement | null = null

const AMBIENCE_FILES: Record<AmbienceType, string> = {
  rain: '/ambience/rain.mp3',
  ocean: '/ambience/ocean.mp3',
  forest: '/ambience/forest.mp3',
  bowls: '/ambience/bowls.mp3',
}

export function startAmbience(type: AmbienceType, volume: number): void {
  stopAmbience()

  audioEl = new Audio(AMBIENCE_FILES[type])
  audioEl.loop = true
  audioEl.volume = volume
  audioEl.play().catch(() => { /* autoplay blocked — voice play() covers the gesture */ })
}

export function setAmbienceVolume(volume: number): void {
  if (audioEl) audioEl.volume = volume
}

export function pauseAmbience(): void {
  if (audioEl) audioEl.pause()
}

export function resumeAmbience(): void {
  if (audioEl) audioEl.play().catch(() => {})
}

export function stopAmbience(): void {
  if (audioEl) {
    audioEl.pause()
    audioEl.src = ''
    audioEl = null
  }
}
