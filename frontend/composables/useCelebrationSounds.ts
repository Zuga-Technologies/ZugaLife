/**
 * useCelebrationSounds — Web Audio API synthesized celebration sounds.
 *
 * No audio files needed. Generates short, satisfying bleeps/chimes procedurally.
 * Mobile-safe: AudioContext created on first user gesture (click/tap).
 */

let _ctx: AudioContext | null = null

function getCtx(): AudioContext | null {
  if (_ctx) return _ctx
  try {
    _ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
    return _ctx
  } catch {
    return null
  }
}

function playTone(freq: number, duration: number, type: OscillatorType = 'sine', gain = 0.15) {
  const ctx = getCtx()
  if (!ctx) return

  const osc = ctx.createOscillator()
  const vol = ctx.createGain()

  osc.type = type
  osc.frequency.setValueAtTime(freq, ctx.currentTime)

  vol.gain.setValueAtTime(0, ctx.currentTime)
  vol.gain.linearRampToValueAtTime(gain, ctx.currentTime + 0.02)
  vol.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration)

  osc.connect(vol)
  vol.connect(ctx.destination)

  osc.start(ctx.currentTime)
  osc.stop(ctx.currentTime + duration)
}

// --- Public sound effects ---

/** Short ascending bleep for XP gain */
export function playXpSound() {
  playTone(523, 0.12, 'sine', 0.12)     // C5
  setTimeout(() => playTone(659, 0.12, 'sine', 0.12), 60)  // E5
}

/** Two-note chime for badge earned */
export function playBadgeSound() {
  playTone(659, 0.2, 'triangle', 0.15)   // E5
  setTimeout(() => playTone(880, 0.3, 'triangle', 0.15), 120)  // A5
}

/** Triumphant ascending arpeggio for level up */
export function playLevelUpSound() {
  playTone(523, 0.15, 'triangle', 0.12)  // C5
  setTimeout(() => playTone(659, 0.15, 'triangle', 0.12), 100)  // E5
  setTimeout(() => playTone(784, 0.15, 'triangle', 0.12), 200)  // G5
  setTimeout(() => playTone(1047, 0.3, 'triangle', 0.15), 300)  // C6
}

/** Warm streak milestone sound */
export function playStreakSound() {
  playTone(440, 0.15, 'sine', 0.1)       // A4
  setTimeout(() => playTone(554, 0.15, 'sine', 0.1), 80)   // C#5
  setTimeout(() => playTone(659, 0.2, 'sine', 0.12), 160)   // E5
}

/** Jackpot slot-machine payout — rapid ascending cascade + sparkle */
export function playJackpotSound() {
  playTone(523, 0.1, 'sine', 0.12)       // C5
  setTimeout(() => playTone(659, 0.1, 'sine', 0.12), 60)   // E5
  setTimeout(() => playTone(784, 0.1, 'sine', 0.14), 120)  // G5
  setTimeout(() => playTone(1047, 0.15, 'triangle', 0.16), 180) // C6
  setTimeout(() => playTone(1319, 0.15, 'triangle', 0.14), 240) // E6
  setTimeout(() => playTone(1568, 0.3, 'sine', 0.12), 300)  // G6 — sparkle top
  setTimeout(() => playTone(2093, 0.4, 'sine', 0.08), 400)  // C7 — shimmer
}

/** Grand prestige fanfare — ascending arpeggio with harmony */
export function playPrestigeSound() {
  playTone(392, 0.2, 'triangle', 0.1)     // G4
  setTimeout(() => playTone(523, 0.2, 'triangle', 0.12), 120)  // C5
  setTimeout(() => playTone(659, 0.2, 'triangle', 0.12), 240)  // E5
  setTimeout(() => playTone(784, 0.2, 'triangle', 0.14), 360)  // G5
  setTimeout(() => playTone(1047, 0.4, 'triangle', 0.16), 480) // C6
  setTimeout(() => playTone(1319, 0.5, 'sine', 0.12), 600)     // E6 — shimmering top note
}

/**
 * Zugabot signature jingle — the brand sound.
 *
 * Pattern: two quick triangle blips (tech/digital character), short gap,
 * then a warm sine-wave D-major resolution with a high shimmer that fades.
 * Total ~550ms. Distinct from playLevelUpSound (single arpeggio) and
 * playBadgeSound (two-note chime). Use this for general action confirmations.
 */
export function playZugabotJingle() {
  // Two quick "blips" — tech feel
  playTone(494, 0.08, 'triangle', 0.10)                          // B4
  setTimeout(() => playTone(494, 0.08, 'triangle', 0.10), 100)   // B4 again
  // Warm chord-like resolution (D major, slight stagger for shimmer)
  setTimeout(() => playTone(587, 0.25, 'sine', 0.12), 220)        // D5
  setTimeout(() => playTone(740, 0.25, 'sine', 0.10), 240)        // F#5
  setTimeout(() => playTone(880, 0.30, 'sine', 0.09), 320)        // A5
  // Sparkle tail
  setTimeout(() => playTone(1480, 0.35, 'sine', 0.05), 420)       // F#6 — soft overtone
}
