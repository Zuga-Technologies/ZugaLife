# Meditation Ambience — Layered Stems Engine

**Date:** 2026-05-05
**Status:** Design approved, awaiting implementation plan
**Owners:** Buga (product), Claude session (engine)
**Touches:** `ZugaLife/frontend/ambience.ts`, `ZugaLife/frontend/public/ambience/*`, `ZugaLife/frontend/tabs/MeditateTab.vue` (consumer, no API change)

## Problem

The current meditation ambience engine (`ZugaLife/frontend/ambience.ts`) loops a single ~60s mp3 per ambience type using a dual-track crossfade to hide the loop seam. In a 10–25 minute meditation session this still telegraphs as "on repeat" — the same wave, the same bird call, the same bowl strike recurs at predictable intervals, breaking immersion. The bowls ambience is the most obviously broken because it's a discrete percussive sample being treated as a continuous texture.

Buga's framing: *"All of the ambient noises need upgrading. They all have the same issue — they need to sound more realistic for what they are."*

## Goal

Rebuild the ambience engine so that a 25-minute session has no audibly recurring elements, and so that each ambience reflects the acoustic character of its real-world counterpart (rain is continuous; ocean has rhythm; forest has sparse intermittent events; bowls are punctuated strikes over a drone).

Quality bar: should pass for a top-tier meditation app (Calm, Headspace, Insight Timer).

## Approach

**Layered stems** — replace the single-file-per-ambience model with a per-ambience composition of:
- *Beds*: 0..N continuous loops, each starting at a random offset with independent slow volume drift, so the combination never aligns the same way twice.
- *Event pools*: 0..M stochastic schedulers that fire discrete samples at randomized intervals with optional probability gating.

Mathematically, with all loops at independent random offsets and durations, the combined waveform's recurrence period is the LCM of all stem durations — measured in hours, not minutes.

Other approaches considered and rejected:
- *Single longer file (5–10 min)*: still loops in a 25-min session; doesn't solve bowls; asset-only, no architectural improvement.
- *Granular synthesis via Web Audio API*: pro-audio approach, much higher complexity, unjustified for v1.
- *External streaming (Mubert API)*: $199/mo, music-genre-focused, weak on pure nature.

## Architecture

### Public API (unchanged)

`MeditateTab.vue` is the only consumer. The public surface is preserved:

```ts
startAmbience(type: AmbienceType, volume: number): void
setAmbienceVolume(volume: number): void
pauseAmbience(): void
resumeAmbience(): void
stopAmbience(): void
```

`AmbienceType` stays `'rain' | 'ocean' | 'forest' | 'bowls'`.

### Internal config schema

```ts
type StemConfig = {
  file: string              // path under /ambience/<type>/
  baseVolume: number        // 0..1, hand-tuned per stem
  driftRange: number        // 0..1, ± fraction around baseVolume
  loopMode: 'simple-loop' | 'crossfade'  // 'simple-loop' for genuinely seamless stems
}

type EventPool = {
  pool: string[]            // sample filenames
  intervalMin: number       // ms
  intervalMax: number       // ms
  probability: number       // 0..1, default 1.0 — chance per slot
  volumeJitter: number      // ± fraction, default 0
}

type AmbienceConfig = {
  beds: StemConfig[]
  events: EventPool[]
}

const AMBIENCE_MIX: Record<AmbienceType, AmbienceConfig>
```

### Per-ambience recipes

| Ambience | Beds | Event pools | Total assets | Notes |
|---|---|---|---|---|
| **Rain** | `rain-bed`, `drips-close`, `wind-through-trees` (3) | `thunder` (2 samples, 120–300s, prob=0.4) | 5 | Continuous-dominant; thunder rare |
| **Ocean** | `shore-wind` (1) | `wave-crash` (4 samples, 15–45s, prob=1.0); `gulls-distant` (2 samples, 90–240s, prob=0.3) | 7 | Rhythmic surf events on a quiet bed |
| **Forest** | `insect-hum`, `leaves-wind` (2) | `bird-chirp` (5 samples, 8–30s, prob=0.6); `gust-rustle` (2 samples, 45–120s, prob=1.0) | 9 | Most asset-heavy; reflects acoustic variety |
| **Bowls** | `drone-bed` (1) | `strike` (3 samples, 30–120s, prob=1.0, volumeJitter=0.15) | 4 | Drone always; strikes punctuate |

### Engine internals

One unified composer reads `AmbienceConfig` and orchestrates:

- **Bed playback**: each bed → one persistent `HTMLAudioElement` with `loop=true`, `currentTime = Math.random() * duration` on start. A per-stem drift loop runs on `setInterval(8–15s)`: pick a new target volume in `[base*(1-driftRange), base*(1+driftRange)]`, ramp linearly to it. Phase-offset per stem so drifts are never in sync.
- **Event scheduling**: per pool, a `setTimeout` chain re-armed after each fire. On fire: roll `probability`; if pass, pick a sample (avoiding immediate repeat of last fired), create a fresh one-shot `HTMLAudioElement`, set volume = `globalVolume * (1 + jitter)`, play. Schedule next slot at `random(intervalMin, intervalMax)`.
- **First event delay**: events do not fire at t=0. First slot's delay = `random(intervalMin, intervalMax)`. Justification: voice guidance plays from t=0; an immediate event clashes with the intro voice.

### File layout

```
frontend/public/ambience/
  rain/      rain-bed.webm  drips-close.webm  wind-through-trees.webm  thunder-1.webm  thunder-2.webm
  ocean/     shore-wind.webm  wave-crash-1.webm  wave-crash-2.webm  wave-crash-3.webm  wave-crash-4.webm
             gull-1.webm  gull-2.webm
  forest/    insect-hum.webm  leaves-wind.webm  bird-1.webm  bird-2.webm  bird-3.webm  bird-4.webm  bird-5.webm
             gust-1.webm  gust-2.webm
  bowls/     drone-bed.webm  strike-low.webm  strike-mid.webm  strike-high.webm
```

### File format

Opus in WebM container at ~96 kbps. ~Half the size of equivalent-quality mp3 for ambient material. Universal modern-browser support. No mp3 fallback unless device-specific gaps surface in QA.

### File length

Beds: 90–180s each. Event samples: natural duration (1–10s typically).

### Total payload

~25 files across all four ambiences, ~30–40 MB total at 96 kbps Opus. **Lazy-loaded per session** — only the active ambience's stems are fetched. Per-session download: ~3 MB (bowls) to ~12 MB (forest).

## Lifecycle

### Loading

`startAmbience(type, vol)` issues `Promise.all(stems.map(preload))` where `preload` resolves on `canplaythrough` (or rejects on error). Voice playback in `MeditateTab.vue` does **not block** on ambience preload. Once preloads resolve, beds fade in 0 → target over 1.5s.

### Per-stem failure

A failed stem (404, decode error) logs a warning and is skipped. The remaining stems still play. If *all* stems fail, the ambience falls back silently to no-audio and surfaces a single console warning. Meditation continues.

### Pause / Resume

Pause: clear all drift timers and the event scheduler timeout, call `.pause()` on every bed and any in-flight event element. Resume: restart drift timers (with fresh random targets, not mid-ramp resume), re-arm scheduler with fresh random interval, call `.play()` on each bed.

### Stop

Linear 1.5s fade-out on all beds, then pause + detach (`el.src = ''; el = null`). Pending scheduled events are cancelled. Active event samples finish naturally (already short).

### Volume slider mid-session

`setAmbienceVolume(v)` updates `globalVolume`. Drift loops read `globalVolume` on each ramp step → propagates within next 8–15s drift cycle. For deltas >0.3, force immediate re-ramp to new range. Events pick up new volume on next fire.

### Browser autoplay

First `.play()` requires a user gesture; the existing voice playback in `MeditateTab.vue:659` covers this. All subsequent plays inherit the gesture grant. Existing `.catch(() => {})` swallow stays — autoplay rejection is non-fatal.

### Memory

Event `HTMLAudioElement`s are detached and nulled in their `ended` handler. A 25-min session at typical fire rates produces tens of one-shots — trivial. Beds are 1–9 long-lived elements per session, nulled on stop.

### Tab visibility

Hidden tabs throttle timers to ~1 Hz. Drift continues smoothly; event scheduler may delay a fire by up to 1s — imperceptible. No special handling.

## Testing

### Pure-logic unit tests (vitest)

Pure utilities extracted from the engine, tested deterministically with seeded random:

- `nextStrikeDelay(min, max, rand)` — bounds, distribution
- `pickFromPool(pool, lastFired, rand)` — never repeats immediate prior; handles single-element pool
- `driftStep(current, target, stepSize)` — monotonic, hits target, no overshoot
- `eventFires(probability, rand)` — respects gate; prob=1 always fires; prob=0 never fires

Target: ~40 tests, all deterministic, runtime <1s.

### Engine integration tests

With a stubbed `HTMLAudioElement`:
- `startAmbience(type)` registers the correct number of beds + scheduler timeouts per recipe
- `pauseAmbience` clears every timer and pauses every element
- `stopAmbience` detaches every element (no leaks)
- Single-stem failure does not abort the ambience

### Manual smoke

One 25-minute meditation per ambience on headphones, listening for audible loop points or unnaturally regular events. Done by Buga before each ambience flips from legacy single-file to layered config. This is the only honest test of the seam-free claim.

## Migration & rollout

Two parallel tracks, either can ship independently.

**Track A — Engine refactor.** Refactor `ambience.ts` against the new `AmbienceConfig` schema. Initial `AMBIENCE_MIX` points each ambience at its **current single mp3 file** as a 1-bed config with `loopMode: 'crossfade'`. Behavior is preserved (modulo the existing dual-track crossfade, replicated via `crossfade` mode). No user-visible change. Engine ships to production without waiting for assets.

**Track B — Asset acquisition.** Source stems per the recommendations in the sourcing report (see Open Questions below for the report reference):
- Rain: Arctura #39827, #39828 (CC-BY) + RyanKingArt #607228 (CC0) from Freesound
- Ocean: amholma #376795 + tim.kahn pack 7955 from Freesound
- Forest: InspectorJ packs from Freesound (CC-BY)
- Bowls: TERA MANGALA Solfeggio Frequencies pack ($6) on Bandcamp + the_very_Real_Horst pack 12242 on Freesound

Encode to Opus/WebM, place in `frontend/public/ambience/<type>/`, update `AMBIENCE_MIX` config one ambience at a time. Each ambience flips from 1-bed legacy config to N-bed layered config in a one-line change.

### Attribution

Add to ZugaLife's `/about` page or settings footer:

> Nature sounds courtesy of Freesound.org contributors (CC-BY 3.0). Singing bowl recordings by TERA MANGALA.

Satisfies all CC-BY licenses in one place. Bowls Bandcamp purchases don't legally require attribution but it's polite.

### Rollback

- Asset-config commit revertable per ambience (engine keeps working with whatever stems remain).
- Worst-case: revert the Track A engine commit, restoring today's `ambience.ts`.

## Out of scope

- New ambience types (café, fireplace, etc.)
- User-customizable mixes
- Backend stem delivery (CDN, signed URLs) — stems ship as static files
- ZugaTokens-gated premium ambiences

## Open questions / dependencies

- Asset acquisition is on Buga (Freesound + Bandcamp purchases). Engineering on Track A does not block on this.
- Sourcing research full report (cited): produced in the brainstorm session 2026-05-05 by `researcher` agent. Key recommendation: Freesound (CC-BY) for rain/ocean/forest + TERA MANGALA (one-time Bandcamp purchase) for bowls. Total spend under $25, no subscription, unambiguous commercial license.
- Hard excludes per the research: Artlist SFX, Loopmasters, ElevenLabs SFX (all explicitly prohibit standalone-file commercial delivery, which is what an ambience engine streaming to a browser is).

## Definition of done

1. `ambience.ts` refactored to `AmbienceConfig` schema; existing single-file mp3s wrapped as 1-bed configs; behavior preserved; ships to production. (Track A)
2. Vitest suite for pure utilities passes (~40 tests).
3. Engine integration tests for lifecycle pass.
4. At least one ambience (likely rain) flipped to full layered config with new stems; passes Buga's 25-min headphone smoke. (Track B partial)
5. Remaining three ambiences flipped to layered configs as their assets become available. (Track B complete)
6. Attribution line live on `/about` or footer.
