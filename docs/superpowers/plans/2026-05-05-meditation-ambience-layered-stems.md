# Meditation Ambience — Layered Stems Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-file-per-ambience meditation backing audio with a layered-stems engine so 25-minute sessions never audibly repeat.

**Architecture:** Two-track rollout. Track A refactors `frontend/ambience.ts` into a `frontend/ambience/` module that supports per-ambience compositions of continuous beds + stochastic event pools, while preserving today's behavior (initial config wraps existing single mp3s as 1-bed configs). Track B flips each ambience to its full layered config when stems are sourced. The public API consumed by `MeditateTab.vue` does not change.

**Tech Stack:** Vue 3 + TypeScript + Vite. Browser `HTMLAudioElement` for playback. Throwaway `npx tsx --test` for one-shot math validation (no persistent test-framework dep added). Audio assets are static files under `frontend/public/ambience/<type>/`. Audio format: Opus in WebM at ~96 kbps for new stems; legacy mp3s remain valid until per-ambience flip.

**Spec:** `ZugaLife/docs/superpowers/specs/2026-05-05-meditation-ambience-layered-stems-design.md`

---

## File Structure

**Created:**
- `frontend/ambience/index.ts` — public API façade + composer that wires `BedManager` and `EventScheduler` per active session. Default export keeps existing import path (`from '../ambience'`) working.
- `frontend/ambience/config.ts` — types (`AmbienceType`, `StemConfig`, `EventPool`, `AmbienceConfig`) and the `AMBIENCE_MIX` map.
- `frontend/ambience/utils.ts` — pure utility functions: `nextEventDelay`, `pickFromPool`, `eventFires`, `nextDriftTarget`, `jitterVolume`. No DOM, no globals.
- `frontend/ambience/beds.ts` — `BedManager` class. Owns per-bed `HTMLAudioElement` lifecycle, random-offset start, drift loop, and crossfade-mode dual-track swap (preserves today's behavior for `loopMode: 'crossfade'`).
- `frontend/ambience/events.ts` — `EventScheduler` class. Per-pool stochastic scheduler; one-shot `HTMLAudioElement` per fire with volume jitter, anti-immediate-repeat sample selection.

**Deleted:**
- `frontend/ambience.ts` (replaced by the directory module).

**Modified:**
- `frontend/LifeSettings.vue` — adds an attribution credits section near the bottom of the settings panel (one paragraph). Required by CC-BY licenses on Freesound stems.

**Not modified:**
- `frontend/tabs/MeditateTab.vue` — preserved import path (`from '../ambience'`) resolves to the new `frontend/ambience/index.ts`.
- Backend, database, all other Vue components.

**Throwaway (created and deleted within Task 3):**
- `frontend/ambience/utils.test.ts` — node `--test` smoke for the pure utilities.

---

## Tracks

- **Track A — Engine refactor (Tasks 1–10).** Behavior-preserving. Ships independent of any new audio assets. Each ambience continues to play its current single mp3 file but now wired through the new engine in `loopMode: 'crossfade'` (replicates today's dual-track crossfade).
- **Track B — Asset migrations (Tasks 11–15).** Done one ambience at a time as Buga sources stems. Each is a config-only change in `config.ts` plus dropping new files into `public/ambience/<type>/`. Order suggested: bowls → rain → ocean → forest (smallest asset count first).

---

# TRACK A — Engine refactor

### Task 1: Define types and `AMBIENCE_MIX` (legacy-config seed)

**Files:**
- Create: `frontend/ambience/config.ts`

- [ ] **Step 1: Write `config.ts`**

```ts
// frontend/ambience/config.ts
export type AmbienceType = 'rain' | 'ocean' | 'forest' | 'bowls'

export interface StemConfig {
  /** Absolute URL path under /public, e.g. "/ambience/rain.mp3" or "/ambience/rain/bed.webm" */
  file: string
  /** 0..1 — hand-tuned per stem; multiplied by user's global volume */
  baseVolume: number
  /** 0..1 — drift swings volume in [base*(1-range), base*(1+range)]. 0 = no drift */
  driftRange: number
  /** 'simple-loop' uses HTMLAudioElement.loop=true (only for genuinely seamless stems).
   *  'crossfade' alternates two elements with fade-overlap (used for legacy single-file stems
   *   and any new stem whose recording isn't pre-edited as a seamless loop). */
  loopMode: 'simple-loop' | 'crossfade'
}

export interface EventPool {
  /** URL paths of sample files in this pool */
  pool: string[]
  /** ms — minimum delay between consecutive fires */
  intervalMin: number
  /** ms — maximum delay between consecutive fires */
  intervalMax: number
  /** 0..1 — chance per slot that a fire actually plays (the slot is consumed either way).
   *  Defaults to 1.0 (every slot fires). Use <1 for irregular events like thunder. */
  probability: number
  /** 0..1 — fire volume = globalVolume * (1 + uniformInRange(-jitter, +jitter)). Default 0 */
  volumeJitter: number
}

export interface AmbienceConfig {
  beds: StemConfig[]
  events: EventPool[]
}

/** Initial seed: legacy single-file behavior preserved. Each ambience flips to a
 *  full layered config in Track B once its stems are sourced. */
export const AMBIENCE_MIX: Record<AmbienceType, AmbienceConfig> = {
  rain: {
    beds: [{ file: '/ambience/rain.mp3', baseVolume: 1.0, driftRange: 0, loopMode: 'crossfade' }],
    events: [],
  },
  ocean: {
    beds: [{ file: '/ambience/ocean.mp3', baseVolume: 1.0, driftRange: 0, loopMode: 'crossfade' }],
    events: [],
  },
  forest: {
    beds: [{ file: '/ambience/forest.mp3', baseVolume: 1.0, driftRange: 0, loopMode: 'crossfade' }],
    events: [],
  },
  bowls: {
    beds: [{ file: '/ambience/bowls.mp3', baseVolume: 1.0, driftRange: 0, loopMode: 'crossfade' }],
    events: [],
  },
}

/** Crossfade overlap duration in seconds (legacy parity). */
export const CROSSFADE_DURATION_SEC = 4

/** Drift cycle bounds (ms). New target volume picked every random in this range. */
export const DRIFT_INTERVAL_MIN_MS = 8000
export const DRIFT_INTERVAL_MAX_MS = 15000
```

- [ ] **Step 2: Commit**

```bash
git add frontend/ambience/config.ts
git commit -m "feat(ambience): add layered-stems config schema"
```

---

### Task 2: Pure utilities

**Files:**
- Create: `frontend/ambience/utils.ts`

- [ ] **Step 1: Write `utils.ts`**

```ts
// frontend/ambience/utils.ts
//
// All functions here are pure and accept an injectable `rand` (default Math.random)
// so they're deterministically testable.

type Rand = () => number

/** Returns a uniformly random delay in [intervalMin, intervalMax] (ms). */
export function nextEventDelay(intervalMin: number, intervalMax: number, rand: Rand = Math.random): number {
  if (intervalMax < intervalMin) throw new Error('intervalMax < intervalMin')
  return intervalMin + rand() * (intervalMax - intervalMin)
}

/** Picks a random element from `pool`, avoiding `lastFired` if the pool has >1 element.
 *  If pool has exactly 1 element, returns it (immediate repeat unavoidable).
 *  Throws if pool is empty. */
export function pickFromPool<T>(pool: readonly T[], lastFired: T | null, rand: Rand = Math.random): T {
  if (pool.length === 0) throw new Error('pickFromPool: pool is empty')
  if (pool.length === 1) return pool[0]
  const candidates = lastFired === null ? pool : pool.filter(x => x !== lastFired)
  // candidates.length is guaranteed >= 1 here (pool has >=2, filtered out at most 1)
  const idx = Math.floor(rand() * candidates.length)
  return candidates[idx]
}

/** Returns true if a probabilistic event fires this slot. probability=1 always true; 0 always false. */
export function eventFires(probability: number, rand: Rand = Math.random): boolean {
  if (probability <= 0) return false
  if (probability >= 1) return true
  return rand() < probability
}

/** Picks a new drift target volume in [base*(1-range), base*(1+range)]. */
export function nextDriftTarget(base: number, driftRange: number, rand: Rand = Math.random): number {
  if (driftRange <= 0) return base
  const lo = base * (1 - driftRange)
  const hi = base * (1 + driftRange)
  return lo + rand() * (hi - lo)
}

/** Returns base * (1 + uniformInRange(-jitter, +jitter)). jitter=0 returns base unchanged. */
export function jitterVolume(base: number, jitter: number, rand: Rand = Math.random): number {
  if (jitter <= 0) return base
  const offset = (rand() * 2 - 1) * jitter
  return base * (1 + offset)
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/ambience/utils.ts
git commit -m "feat(ambience): add pure utility functions for layered engine"
```

---

### Task 3: Throwaway smoke test for utilities

**Files:**
- Create: `frontend/ambience/utils.test.ts` (deleted after this task)

- [ ] **Step 1: Write the smoke test**

```ts
// frontend/ambience/utils.test.ts — THROWAWAY: deleted after one passing run
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nextEventDelay, pickFromPool, eventFires, nextDriftTarget, jitterVolume } from './utils.ts'

// Seeded PRNG (mulberry32) for determinism
function seeded(seed: number): () => number {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6D2B79F5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

test('nextEventDelay stays in bounds across 1000 samples', () => {
  const r = seeded(1)
  for (let i = 0; i < 1000; i++) {
    const d = nextEventDelay(30_000, 120_000, r)
    assert.ok(d >= 30_000 && d <= 120_000, `out of bounds: ${d}`)
  }
})

test('nextEventDelay throws when max < min', () => {
  assert.throws(() => nextEventDelay(100, 50))
})

test('pickFromPool never returns lastFired when pool has >1 element', () => {
  const r = seeded(2)
  const pool = ['a', 'b', 'c']
  let last: string | null = null
  for (let i = 0; i < 200; i++) {
    const picked = pickFromPool(pool, last, r)
    assert.notEqual(picked, last)
    last = picked
  }
})

test('pickFromPool returns the only element for size-1 pool (even matching lastFired)', () => {
  assert.equal(pickFromPool(['x'], 'x'), 'x')
})

test('pickFromPool throws on empty pool', () => {
  assert.throws(() => pickFromPool([], null))
})

test('eventFires probability=1 always true, =0 always false', () => {
  const r = seeded(3)
  for (let i = 0; i < 100; i++) {
    assert.equal(eventFires(1, r), true)
    assert.equal(eventFires(0, r), false)
  }
})

test('eventFires probability=0.4 fires roughly 40% of the time over 10k samples', () => {
  const r = seeded(4)
  let hits = 0
  for (let i = 0; i < 10_000; i++) if (eventFires(0.4, r)) hits++
  // 40% ± 3% tolerance for 10k samples
  assert.ok(hits > 3700 && hits < 4300, `expected ~4000 hits, got ${hits}`)
})

test('nextDriftTarget stays in [base*(1-range), base*(1+range)]', () => {
  const r = seeded(5)
  for (let i = 0; i < 1000; i++) {
    const t = nextDriftTarget(0.5, 0.2, r)
    assert.ok(t >= 0.5 * 0.8 - 1e-9 && t <= 0.5 * 1.2 + 1e-9, `out of bounds: ${t}`)
  }
})

test('nextDriftTarget driftRange=0 returns base exactly', () => {
  assert.equal(nextDriftTarget(0.7, 0), 0.7)
})

test('jitterVolume jitter=0 returns base exactly', () => {
  assert.equal(jitterVolume(0.5, 0), 0.5)
})

test('jitterVolume stays in [base*(1-jitter), base*(1+jitter)]', () => {
  const r = seeded(6)
  for (let i = 0; i < 1000; i++) {
    const v = jitterVolume(0.6, 0.15, r)
    assert.ok(v >= 0.6 * 0.85 - 1e-9 && v <= 0.6 * 1.15 + 1e-9, `out of bounds: ${v}`)
  }
})
```

- [ ] **Step 2: Run the test via npx tsx**

```bash
cd E:/Programming/ZugaLife/frontend && npx tsx --test ambience/utils.test.ts
```

Expected: all 10 tests pass. Output ends with `# pass 10` (or similar success summary). If any fail, fix `utils.ts` and re-run.

- [ ] **Step 3: Delete the throwaway test file**

```bash
cd E:/Programming/ZugaLife && rm frontend/ambience/utils.test.ts
```

- [ ] **Step 4: Verify deletion**

```bash
cd E:/Programming/ZugaLife && ls frontend/ambience/
```

Expected: only `config.ts` and `utils.ts` listed (no `utils.test.ts`).

- [ ] **Step 5: Commit (no-op for deleted untracked file — utils.ts already committed in Task 2)**

If the deletion left git state dirty, `git status` should show nothing because the throwaway file was never `git add`ed. No commit needed.

---

### Task 4: `BedManager` — bed playback with drift and crossfade

**Files:**
- Create: `frontend/ambience/beds.ts`

- [ ] **Step 1: Write `beds.ts`**

```ts
// frontend/ambience/beds.ts
import {
  type StemConfig,
  CROSSFADE_DURATION_SEC,
  DRIFT_INTERVAL_MIN_MS,
  DRIFT_INTERVAL_MAX_MS,
} from './config'
import { nextDriftTarget, nextEventDelay } from './utils'

interface ActiveBed {
  config: StemConfig
  /** For simple-loop: the only audio element. For crossfade: currently-foreground element. */
  primary: HTMLAudioElement
  /** crossfade-mode only: the off-screen element that fades in next */
  secondary: HTMLAudioElement | null
  driftTimer: ReturnType<typeof setTimeout> | null
  crossfadeTimer: ReturnType<typeof setInterval> | null
  /** Current effective volume of whichever element is foreground, BEFORE multiplying by globalVolume.
   *  i.e. this is in baseVolume-relative units, range roughly [base*(1-driftRange), base*(1+driftRange)]. */
  currentDriftedBase: number
}

export class BedManager {
  private beds: ActiveBed[] = []
  private globalVolume = 0.4
  private paused = false

  /** Loads and starts every bed. Per-stem load failures are logged and skipped. */
  async start(stems: StemConfig[], globalVolume: number): Promise<void> {
    this.globalVolume = globalVolume
    this.paused = false
    const results = await Promise.allSettled(stems.map((s) => this.createBed(s)))
    for (const r of results) {
      if (r.status === 'fulfilled') {
        const bed = r.value
        this.beds.push(bed)
        bed.primary.play().catch(() => { /* autoplay rejection — voice gesture covers next play */ })
        this.scheduleDrift(bed)
        if (bed.config.loopMode === 'crossfade') this.startCrossfadeLoop(bed)
      } else {
        console.warn('[ambience] bed load failed:', r.reason)
      }
    }
  }

  setGlobalVolume(v: number): void {
    const prev = this.globalVolume
    this.globalVolume = v
    // For big jumps, force immediate re-ramp so user hears the change quickly.
    if (Math.abs(v - prev) > 0.3) {
      for (const bed of this.beds) this.applyVolume(bed)
    }
    // Smaller changes propagate within next drift cycle naturally.
  }

  pause(): void {
    this.paused = true
    for (const bed of this.beds) {
      if (bed.driftTimer) { clearTimeout(bed.driftTimer); bed.driftTimer = null }
      if (bed.crossfadeTimer) { clearInterval(bed.crossfadeTimer); bed.crossfadeTimer = null }
      bed.primary.pause()
      bed.secondary?.pause()
    }
  }

  resume(): void {
    this.paused = false
    for (const bed of this.beds) {
      // Re-pick a fresh drift target rather than resuming mid-ramp.
      bed.currentDriftedBase = nextDriftTarget(bed.config.baseVolume, bed.config.driftRange)
      this.applyVolume(bed)
      bed.primary.play().catch(() => {})
      this.scheduleDrift(bed)
      if (bed.config.loopMode === 'crossfade') this.startCrossfadeLoop(bed)
    }
  }

  /** 1.5s linear fade-out then detach. */
  async stop(): Promise<void> {
    const FADE_MS = 1500
    const STEPS = 30
    const stepMs = FADE_MS / STEPS
    // Cancel timers immediately so no new drift/crossfade kicks in during fade
    for (const bed of this.beds) {
      if (bed.driftTimer) { clearTimeout(bed.driftTimer); bed.driftTimer = null }
      if (bed.crossfadeTimer) { clearInterval(bed.crossfadeTimer); bed.crossfadeTimer = null }
    }
    const startVolumes = this.beds.map((b) => ({
      primary: b.primary.volume,
      secondary: b.secondary?.volume ?? 0,
    }))
    for (let s = 1; s <= STEPS; s++) {
      const k = 1 - s / STEPS
      for (let i = 0; i < this.beds.length; i++) {
        const b = this.beds[i]
        b.primary.volume = startVolumes[i].primary * k
        if (b.secondary) b.secondary.volume = startVolumes[i].secondary * k
      }
      await new Promise((r) => setTimeout(r, stepMs))
    }
    for (const bed of this.beds) {
      bed.primary.pause(); bed.primary.src = ''
      if (bed.secondary) { bed.secondary.pause(); bed.secondary.src = '' }
    }
    this.beds = []
  }

  // ─── private ─────────────────────────────────────────────────────────────

  private async createBed(config: StemConfig): Promise<ActiveBed> {
    const primary = new Audio(config.file)
    primary.preload = 'auto'
    if (config.loopMode === 'simple-loop') primary.loop = true
    await this.waitCanPlay(primary)
    if (!isNaN(primary.duration) && primary.duration > 0) {
      primary.currentTime = Math.random() * primary.duration
    }
    const initialDriftedBase = nextDriftTarget(config.baseVolume, config.driftRange)
    primary.volume = initialDriftedBase * this.globalVolume

    let secondary: HTMLAudioElement | null = null
    if (config.loopMode === 'crossfade') {
      secondary = new Audio(config.file)
      secondary.preload = 'auto'
      secondary.volume = 0
      await this.waitCanPlay(secondary)
    }
    return {
      config,
      primary,
      secondary,
      driftTimer: null,
      crossfadeTimer: null,
      currentDriftedBase: initialDriftedBase,
    }
  }

  private waitCanPlay(el: HTMLAudioElement): Promise<void> {
    return new Promise((resolve, reject) => {
      const onReady = () => { cleanup(); resolve() }
      const onError = () => { cleanup(); reject(new Error(`Failed to load ${el.src}`)) }
      const cleanup = () => {
        el.removeEventListener('canplaythrough', onReady)
        el.removeEventListener('error', onError)
      }
      el.addEventListener('canplaythrough', onReady, { once: true })
      el.addEventListener('error', onError, { once: true })
    })
  }

  /** Updates the bed's foreground element to the current drifted volume * globalVolume. */
  private applyVolume(bed: ActiveBed): void {
    bed.primary.volume = bed.currentDriftedBase * this.globalVolume
  }

  private scheduleDrift(bed: ActiveBed): void {
    if (this.paused) return
    if (bed.config.driftRange <= 0) return // no drift configured
    const delay = nextEventDelay(DRIFT_INTERVAL_MIN_MS, DRIFT_INTERVAL_MAX_MS)
    bed.driftTimer = setTimeout(() => {
      const newTarget = nextDriftTarget(bed.config.baseVolume, bed.config.driftRange)
      this.rampVolume(bed, newTarget, delay)
    }, delay)
  }

  /** Linear ramp of bed.currentDriftedBase from current to `target` over `durationMs`,
   *  applying globalVolume on each step. Schedules the next drift cycle on completion. */
  private rampVolume(bed: ActiveBed, target: number, durationMs: number): void {
    const STEPS = 20
    const stepMs = durationMs / STEPS
    const start = bed.currentDriftedBase
    let s = 0
    const tick = () => {
      if (this.paused) return
      s++
      const k = s / STEPS
      bed.currentDriftedBase = start + (target - start) * k
      this.applyVolume(bed)
      if (s < STEPS) {
        bed.driftTimer = setTimeout(tick, stepMs)
      } else {
        this.scheduleDrift(bed)
      }
    }
    bed.driftTimer = setTimeout(tick, stepMs)
  }

  /** Legacy-compatible dual-track crossfade (replicates current ambience.ts behavior). */
  private startCrossfadeLoop(bed: ActiveBed): void {
    if (!bed.secondary) return
    bed.crossfadeTimer = setInterval(() => {
      if (this.paused || !bed.secondary) return
      const remaining = bed.primary.duration - bed.primary.currentTime
      if (isNaN(remaining) || remaining > CROSSFADE_DURATION_SEC) return
      // Begin crossfade: bring secondary in, fade primary out
      const next = bed.secondary
      next.currentTime = 0
      next.volume = 0
      next.play().catch(() => {})
      const STEPS = 20
      const stepMs = (CROSSFADE_DURATION_SEC * 1000) / STEPS
      const startVol = bed.currentDriftedBase * this.globalVolume
      let step = 0
      const fade = setInterval(() => {
        step++
        const k = step / STEPS
        next.volume = k * startVol
        bed.primary.volume = (1 - k) * startVol
        if (step >= STEPS) {
          clearInterval(fade)
          bed.primary.pause()
          bed.primary.currentTime = 0
          // Swap roles: previous secondary is now primary
          const oldPrimary = bed.primary
          bed.primary = next
          bed.secondary = oldPrimary
        }
      }, stepMs)
    }, 500)
  }
}
```

- [ ] **Step 2: Type-check the file**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors. If errors reference `beds.ts`, fix and re-run.

- [ ] **Step 3: Commit**

```bash
git add frontend/ambience/beds.ts
git commit -m "feat(ambience): add BedManager with drift and crossfade modes"
```

---

### Task 5: `EventScheduler` — stochastic sample firing

**Files:**
- Create: `frontend/ambience/events.ts`

- [ ] **Step 1: Write `events.ts`**

```ts
// frontend/ambience/events.ts
import { type EventPool } from './config'
import { nextEventDelay, pickFromPool, eventFires, jitterVolume } from './utils'

interface ActivePool {
  config: EventPool
  timer: ReturnType<typeof setTimeout> | null
  lastFired: string | null
  /** In-flight one-shot elements; we hold refs only to be able to cancel/null on stop. */
  inFlight: Set<HTMLAudioElement>
}

export class EventScheduler {
  private pools: ActivePool[] = []
  private globalVolume = 0.4
  private paused = false

  start(pools: EventPool[], globalVolume: number): void {
    this.globalVolume = globalVolume
    this.paused = false
    for (const cfg of pools) {
      const p: ActivePool = { config: cfg, timer: null, lastFired: null, inFlight: new Set() }
      this.pools.push(p)
      this.scheduleNext(p)
    }
  }

  setGlobalVolume(v: number): void {
    this.globalVolume = v
    // In-flight strikes keep the volume they were fired with; new strikes pick up the new volume.
  }

  pause(): void {
    this.paused = true
    for (const p of this.pools) {
      if (p.timer) { clearTimeout(p.timer); p.timer = null }
      // Active in-flight strikes pause; they'll resume from where they paused (browser default).
      for (const el of p.inFlight) el.pause()
    }
  }

  resume(): void {
    this.paused = false
    for (const p of this.pools) {
      // Re-arm with a fresh interval rather than resuming a mid-flight scheduled timer.
      this.scheduleNext(p)
      for (const el of p.inFlight) el.play().catch(() => {})
    }
  }

  /** Cancels pending fires; in-flight one-shots finish naturally (already short). */
  stop(): void {
    for (const p of this.pools) {
      if (p.timer) { clearTimeout(p.timer); p.timer = null }
      // Detach in-flight elements so they don't keep firing 'ended' on stale closures.
      for (const el of p.inFlight) {
        el.pause(); el.src = ''
      }
      p.inFlight.clear()
    }
    this.pools = []
  }

  // ─── private ─────────────────────────────────────────────────────────────

  private scheduleNext(p: ActivePool): void {
    if (this.paused) return
    const delay = nextEventDelay(p.config.intervalMin, p.config.intervalMax)
    p.timer = setTimeout(() => this.fireSlot(p), delay)
  }

  private fireSlot(p: ActivePool): void {
    if (this.paused) return
    if (eventFires(p.config.probability)) {
      this.fireOne(p)
    }
    // Always reschedule, whether we fired or not (probability gate skips this slot's audio
    // but the next slot's clock still runs).
    this.scheduleNext(p)
  }

  private fireOne(p: ActivePool): void {
    let sample: string
    try {
      sample = pickFromPool(p.config.pool, p.lastFired)
    } catch {
      return // empty pool — config error; silently skip
    }
    p.lastFired = sample
    const el = new Audio(sample)
    el.preload = 'auto'
    el.volume = jitterVolume(this.globalVolume, p.config.volumeJitter)
    p.inFlight.add(el)
    const cleanup = () => {
      p.inFlight.delete(el)
      el.src = ''
    }
    el.addEventListener('ended', cleanup, { once: true })
    el.addEventListener('error', cleanup, { once: true })
    el.play().catch(() => {
      // Autoplay rejected — sample dropped, no retry. Cleanup happens on error event.
    })
  }
}
```

- [ ] **Step 2: Type-check**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/ambience/events.ts
git commit -m "feat(ambience): add EventScheduler for stochastic sample firing"
```

---

### Task 6: Public API façade — `index.ts`

**Files:**
- Create: `frontend/ambience/index.ts`

- [ ] **Step 1: Write `index.ts`**

```ts
// frontend/ambience/index.ts
//
// Public API. MeditateTab.vue imports from '../ambience' and resolves to this file.
// API surface preserved from the prior single-file ambience.ts:
//   startAmbience, setAmbienceVolume, pauseAmbience, resumeAmbience, stopAmbience.

import { AMBIENCE_MIX, type AmbienceType } from './config'
import { BedManager } from './beds'
import { EventScheduler } from './events'

let beds: BedManager | null = null
let events: EventScheduler | null = null
let currentVolume = 0.4

export function startAmbience(type: AmbienceType, volume: number): void {
  // Stop any prior session synchronously enough to not leak elements.
  // We don't await stopAmbience's fade because startAmbience is fire-and-forget.
  stopAmbience()

  const config = AMBIENCE_MIX[type]
  if (!config) {
    console.warn(`[ambience] unknown type: ${type}`)
    return
  }
  currentVolume = volume

  const newBeds = new BedManager()
  const newEvents = new EventScheduler()
  beds = newBeds
  events = newEvents

  // Beds load asynchronously (canplaythrough); events have nothing to preload.
  newBeds.start(config.beds, volume).catch((err) => {
    console.warn('[ambience] bed manager start error:', err)
  })
  newEvents.start(config.events, volume)
}

export function setAmbienceVolume(volume: number): void {
  currentVolume = volume
  beds?.setGlobalVolume(volume)
  events?.setGlobalVolume(volume)
}

export function pauseAmbience(): void {
  beds?.pause()
  events?.pause()
}

export function resumeAmbience(): void {
  beds?.resume()
  events?.resume()
}

export function stopAmbience(): void {
  // Capture refs and null first so a re-entrant startAmbience doesn't race.
  const b = beds
  const e = events
  beds = null
  events = null
  e?.stop()
  // BedManager.stop is async (1.5s fade); fire-and-forget is fine here — we've already
  // detached the reference, so a subsequent startAmbience proceeds with fresh managers.
  b?.stop().catch(() => {})
}
```

- [ ] **Step 2: Type-check**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors. Importantly, `MeditateTab.vue`'s existing imports (`startAmbience`, etc. from `'../ambience'`) should resolve to this new module — TypeScript handles `path/to/ambience` matching `path/to/ambience/index.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/ambience/index.ts
git commit -m "feat(ambience): add public API facade wiring beds + events"
```

---

### Task 7: Delete legacy `ambience.ts`

**Files:**
- Delete: `frontend/ambience.ts`

- [ ] **Step 1: Confirm no references outside the new module**

```bash
cd E:/Programming/ZugaLife && grep -rn "from '\\.\\./ambience'" frontend/ --include='*.ts' --include='*.vue'
```

Expected: only matches in `frontend/tabs/MeditateTab.vue` (any path depth that points at the directory module). The new `frontend/ambience/index.ts` will resolve those imports.

- [ ] **Step 2: Delete the old file**

```bash
cd E:/Programming/ZugaLife && rm frontend/ambience.ts
```

- [ ] **Step 3: Type-check the whole frontend**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors. If any error references `'../ambience'` resolution, the directory module isn't being picked up — verify `frontend/ambience/index.ts` exists.

- [ ] **Step 4: Commit**

```bash
cd E:/Programming/ZugaLife && git add frontend/ambience.ts
git commit -m "refactor(ambience): remove legacy single-file engine"
```

(`git add` of a deleted file stages the deletion.)

---

### Task 8: Build verification

- [ ] **Step 1: Production build**

```bash
cd E:/Programming/ZugaLife/frontend && npm run build
```

Expected: build completes with no TypeScript or Vite errors. The output `dist/` directory is produced.

- [ ] **Step 2: If build fails**

Read the error. The new module references `./config`, `./beds`, `./events`, `./utils` — all relative imports inside `frontend/ambience/`. Fix any path issues, re-run.

---

### Task 9: Manual smoke — behavior parity

This task verifies the engine refactor changed nothing audible. It does NOT verify the layered-stems improvement (that's Track B per ambience).

- [ ] **Step 1: Start the dev server**

```bash
cd E:/Programming/ZugaLife/frontend && npm run dev
```

The server prints a local URL.

- [ ] **Step 2: Smoke each ambience**

For each of `rain`, `ocean`, `forest`, `bowls`:

1. Open the meditation tab.
2. Set ambience to the type.
3. Start a meditation. Listen for 90 seconds.
4. Verify: ambience plays, loops without obvious gap (the legacy crossfade is preserved), pause/resume work, volume slider moves the level.

If any ambience is silent: check the browser DevTools Network tab for a 404 on `/ambience/<type>.mp3`. The file paths in `AMBIENCE_MIX` (`/ambience/rain.mp3` etc.) must match the existing files in `frontend/public/ambience/`.

- [ ] **Step 3: Stop dev server**

Ctrl+C the dev server.

- [ ] **Step 4: Mark Track A complete**

No commit needed (no code changed). Track A is functionally complete: behavior preserved, engine refactored, ready for Track B asset migrations.

---

### Task 10: Add Freesound + TERA MANGALA attribution to LifeSettings

**Files:**
- Modify: `frontend/LifeSettings.vue` (append a credits section near the bottom of the settings panel; placement: above any closing wrapper element)

This is required by CC-BY licenses on Freesound stems before any CC-BY asset is shipped. Track B asset migrations should not start until this is in place.

- [ ] **Step 1: Locate the bottom of the settings template**

```bash
cd E:/Programming/ZugaLife && grep -n "</template>" frontend/LifeSettings.vue
```

Note the line of the closing `</template>`. The credits section goes immediately above the closing wrapper element that's just inside `</template>`.

- [ ] **Step 2: Add the credits section to `LifeSettings.vue`**

Insert this block as the last visual section inside the settings panel's main wrapper (above the closing `</template>`). Use existing class conventions in the file (Tailwind):

```vue
    <!-- ─── Credits ─────────────────────────────────────────────────────── -->
    <section class="mt-8 pt-6 border-t border-white/10 text-xs text-white/50 leading-relaxed">
      <p>
        Nature sounds courtesy of
        <a href="https://freesound.org/" target="_blank" rel="noopener" class="underline hover:text-white/70">Freesound.org</a>
        contributors (CC-BY 3.0). Singing bowl recordings by TERA MANGALA.
      </p>
    </section>
```

- [ ] **Step 3: Type-check + visual confirm**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors. Then start `npm run dev`, open settings, scroll to the bottom, confirm the credits paragraph renders. Stop the dev server.

- [ ] **Step 4: Commit**

```bash
git add frontend/LifeSettings.vue
git commit -m "feat(life): add ambience asset attribution per CC-BY license"
```

---

# TRACK B — Asset migrations (one ambience per task)

Each Track B task is performed when stems for that ambience are sourced, encoded to Opus/WebM, and dropped into `frontend/public/ambience/<type>/`. Asset acquisition is on Buga and is outside the engineering plan.

**Each migration has the same shape:**
1. Verify new stem files exist at the expected paths.
2. Replace that ambience's entry in `AMBIENCE_MIX`.
3. Build + dev server smoke.
4. Buga performs a 25-min headphone smoke meditation in that ambience, listens for any audible loop point.
5. Commit (or revert config and re-source if the smoke fails).

---

### Task 11: Bowls migration (4 stems)

**Prerequisite assets** (placed by Buga before this task starts):
- `frontend/public/ambience/bowls/drone-bed.webm`
- `frontend/public/ambience/bowls/strike-low.webm`
- `frontend/public/ambience/bowls/strike-mid.webm`
- `frontend/public/ambience/bowls/strike-high.webm`

**Files:**
- Modify: `frontend/ambience/config.ts:bowls`

- [ ] **Step 1: Verify stems exist**

```bash
cd E:/Programming/ZugaLife && ls frontend/public/ambience/bowls/
```

Expected output includes all four files above. If any are missing, halt this task and acquire them first.

- [ ] **Step 2: Update `bowls` entry in `AMBIENCE_MIX`**

Replace the current `bowls` entry in `frontend/ambience/config.ts` with:

```ts
  bowls: {
    beds: [
      { file: '/ambience/bowls/drone-bed.webm', baseVolume: 0.7, driftRange: 0.20, loopMode: 'simple-loop' },
    ],
    events: [
      {
        pool: [
          '/ambience/bowls/strike-low.webm',
          '/ambience/bowls/strike-mid.webm',
          '/ambience/bowls/strike-high.webm',
        ],
        intervalMin: 30_000,
        intervalMax: 120_000,
        probability: 1.0,
        volumeJitter: 0.15,
      },
    ],
  },
```

- [ ] **Step 3: Type-check**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json
```

Expected: zero errors.

- [ ] **Step 4: Build**

```bash
cd E:/Programming/ZugaLife/frontend && npm run build
```

Expected: success.

- [ ] **Step 5: Manual smoke (Buga)**

Start `npm run dev`, run a 25-minute meditation with `bowls` ambience on headphones. Pass criteria:
- Drone bed plays continuously, modulated subtly by drift.
- Strikes fire at irregular intervals, never the same one twice in a row.
- No audible repetition of the same exact strike at a regular cadence.
- First strike fires at least 30s after start (not on top of intro voice).

If any criterion fails: revert the config change and re-source assets.

- [ ] **Step 6: Commit**

```bash
git add frontend/ambience/config.ts frontend/public/ambience/bowls/
git commit -m "feat(ambience): bowls layered config (1 drone bed + 3 strike pool)"
```

---

### Task 12: Rain migration (5 stems)

**Prerequisite assets:**
- `frontend/public/ambience/rain/rain-bed.webm`
- `frontend/public/ambience/rain/drips-close.webm`
- `frontend/public/ambience/rain/wind-through-trees.webm`
- `frontend/public/ambience/rain/thunder-1.webm`
- `frontend/public/ambience/rain/thunder-2.webm`

**Files:**
- Modify: `frontend/ambience/config.ts:rain`

- [ ] **Step 1: Verify stems exist**

```bash
cd E:/Programming/ZugaLife && ls frontend/public/ambience/rain/
```

Expected: all five files present.

- [ ] **Step 2: Update `rain` entry**

```ts
  rain: {
    beds: [
      { file: '/ambience/rain/rain-bed.webm',           baseVolume: 1.0, driftRange: 0.10, loopMode: 'simple-loop' },
      { file: '/ambience/rain/drips-close.webm',        baseVolume: 0.5, driftRange: 0.25, loopMode: 'simple-loop' },
      { file: '/ambience/rain/wind-through-trees.webm', baseVolume: 0.6, driftRange: 0.20, loopMode: 'simple-loop' },
    ],
    events: [
      {
        pool: ['/ambience/rain/thunder-1.webm', '/ambience/rain/thunder-2.webm'],
        intervalMin: 120_000,
        intervalMax: 300_000,
        probability: 0.4,
        volumeJitter: 0.10,
      },
    ],
  },
```

- [ ] **Step 3: Type-check + build**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json && npm run build
```

Expected: both succeed.

- [ ] **Step 4: Manual smoke (Buga)**

25-min headphone meditation with `rain` ambience. Pass criteria:
- Rain bed continuous, no audible loop point (cross-bed phasing should mask it).
- Drips and wind layers ride underneath, occasionally rising and receding (drift).
- Thunder rolls heard 1–3 times in a 25-min session, never at predictable intervals.

- [ ] **Step 5: Commit**

```bash
git add frontend/ambience/config.ts frontend/public/ambience/rain/
git commit -m "feat(ambience): rain layered config (3 beds + thunder pool)"
```

---

### Task 13: Ocean migration (7 stems)

**Prerequisite assets:**
- `frontend/public/ambience/ocean/shore-wind.webm`
- `frontend/public/ambience/ocean/wave-crash-1.webm`
- `frontend/public/ambience/ocean/wave-crash-2.webm`
- `frontend/public/ambience/ocean/wave-crash-3.webm`
- `frontend/public/ambience/ocean/wave-crash-4.webm`
- `frontend/public/ambience/ocean/gull-1.webm`
- `frontend/public/ambience/ocean/gull-2.webm`

**Files:**
- Modify: `frontend/ambience/config.ts:ocean`

- [ ] **Step 1: Verify stems exist**

```bash
cd E:/Programming/ZugaLife && ls frontend/public/ambience/ocean/
```

Expected: all seven files present.

- [ ] **Step 2: Update `ocean` entry**

```ts
  ocean: {
    beds: [
      { file: '/ambience/ocean/shore-wind.webm', baseVolume: 0.8, driftRange: 0.15, loopMode: 'simple-loop' },
    ],
    events: [
      {
        pool: [
          '/ambience/ocean/wave-crash-1.webm',
          '/ambience/ocean/wave-crash-2.webm',
          '/ambience/ocean/wave-crash-3.webm',
          '/ambience/ocean/wave-crash-4.webm',
        ],
        intervalMin: 15_000,
        intervalMax: 45_000,
        probability: 1.0,
        volumeJitter: 0.20,
      },
      {
        pool: ['/ambience/ocean/gull-1.webm', '/ambience/ocean/gull-2.webm'],
        intervalMin: 90_000,
        intervalMax: 240_000,
        probability: 0.3,
        volumeJitter: 0.10,
      },
    ],
  },
```

- [ ] **Step 3: Type-check + build**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json && npm run build
```

Expected: both succeed.

- [ ] **Step 4: Manual smoke (Buga)**

25-min headphone meditation with `ocean` ambience. Pass criteria:
- Shore-wind bed always present, gently drifting in volume.
- Wave crashes fire every 15–45s with varied character (4 samples rotated, never same one twice consecutively).
- Distant gulls heard 0–3 times in 25 min, never on a predictable schedule.

- [ ] **Step 5: Commit**

```bash
git add frontend/ambience/config.ts frontend/public/ambience/ocean/
git commit -m "feat(ambience): ocean layered config (1 wind bed + waves + gulls)"
```

---

### Task 14: Forest migration (9 stems)

**Prerequisite assets:**
- `frontend/public/ambience/forest/insect-hum.webm`
- `frontend/public/ambience/forest/leaves-wind.webm`
- `frontend/public/ambience/forest/bird-1.webm` … `bird-5.webm`
- `frontend/public/ambience/forest/gust-1.webm`, `gust-2.webm`

**Files:**
- Modify: `frontend/ambience/config.ts:forest`

- [ ] **Step 1: Verify stems exist**

```bash
cd E:/Programming/ZugaLife && ls frontend/public/ambience/forest/
```

Expected: nine files (`insect-hum`, `leaves-wind`, `bird-1`..`bird-5`, `gust-1`, `gust-2`).

- [ ] **Step 2: Update `forest` entry**

```ts
  forest: {
    beds: [
      { file: '/ambience/forest/insect-hum.webm',  baseVolume: 0.5, driftRange: 0.20, loopMode: 'simple-loop' },
      { file: '/ambience/forest/leaves-wind.webm', baseVolume: 0.7, driftRange: 0.25, loopMode: 'simple-loop' },
    ],
    events: [
      {
        pool: [
          '/ambience/forest/bird-1.webm',
          '/ambience/forest/bird-2.webm',
          '/ambience/forest/bird-3.webm',
          '/ambience/forest/bird-4.webm',
          '/ambience/forest/bird-5.webm',
        ],
        intervalMin: 8_000,
        intervalMax: 30_000,
        probability: 0.6,
        volumeJitter: 0.15,
      },
      {
        pool: ['/ambience/forest/gust-1.webm', '/ambience/forest/gust-2.webm'],
        intervalMin: 45_000,
        intervalMax: 120_000,
        probability: 1.0,
        volumeJitter: 0.10,
      },
    ],
  },
```

- [ ] **Step 3: Type-check + build**

```bash
cd E:/Programming/ZugaLife/frontend && npx vue-tsc --noEmit -p tsconfig.json && npm run build
```

Expected: both succeed.

- [ ] **Step 4: Manual smoke (Buga)**

25-min headphone meditation with `forest` ambience. Pass criteria:
- Insect bed and leaves-wind bed both continuous; wind drift is noticeable as gentle gusting.
- Birds chirp irregularly, all 5 samples eventually heard, never the same one twice in a row.
- Wind gusts heard every 45–120s.

- [ ] **Step 5: Commit**

```bash
git add frontend/ambience/config.ts frontend/public/ambience/forest/
git commit -m "feat(ambience): forest layered config (2 beds + birds + gusts)"
```

---

# Definition of Done

- [ ] Track A complete: `frontend/ambience/` directory module replaces `frontend/ambience.ts`. `MeditateTab.vue` unchanged. All four legacy ambiences sound identical to before the refactor in manual smoke (Task 9). Type-check and production build pass.
- [ ] Task 10 complete: attribution paragraph live in `LifeSettings.vue`.
- [ ] Tasks 11–14 each complete (or pending until their stems are sourced): each ambience flipped from legacy 1-bed to layered config, passes 25-min headphone smoke for non-repetition.

# Out of Scope (per spec)

- New ambience types beyond rain/ocean/forest/bowls.
- User-customizable mixes.
- Backend stem delivery / CDN signing.
- ZugaTokens-gated premium ambiences.
