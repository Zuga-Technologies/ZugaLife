<!--
  BreathColdOpen — 24-second box-breathing cold-open.

  Fires once per UTC day on first /life visit (gating handled by parent).
  Skippable instantly via X button — no friction. After 3 cycles it
  auto-completes and emits 'complete'. The orb scales 0.6 → 1 on inhale,
  1 → 0.6 on exhale, with a soft glow that pulses in sync.

  Design intent: deliver a sub-30s value moment before the dashboard,
  same as Calm/Headspace. Not a meditation — a breath ritual.
-->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { X } from 'lucide-vue-next'

const emit = defineEmits<{ complete: []; skip: [] }>()

// 4s in / 4s out × 3 cycles = 24s total
const PHASE_MS = 4000
const CYCLES = 3
// Smooth exit when the ritual completes naturally — orb expands & fades,
// overlay dims out, THEN we emit complete so the parent unmounts us.
// Skip stays instant — if the user wants out, give them out.
const EXIT_MS = 900

type Phase = 'in' | 'out' | 'done'
const phase = ref<Phase>('in')
const cycle = ref(1)
const exiting = ref(false)

const totalMs = PHASE_MS * 2 * CYCLES
const phaseLabel = computed(() => {
  if (phase.value === 'done') return ''
  return phase.value === 'in' ? 'Breathe in' : 'Breathe out'
})

let phaseTimer: ReturnType<typeof setTimeout> | null = null
let exitTimer: ReturnType<typeof setTimeout> | null = null

function nextPhase() {
  if (phase.value === 'in') {
    phase.value = 'out'
  } else if (phase.value === 'out') {
    phase.value = 'in'
    cycle.value += 1
  }
  if (cycle.value > CYCLES) {
    finish()
    return
  }
  phaseTimer = setTimeout(nextPhase, PHASE_MS)
}

function finish() {
  cleanup()
  // Trigger the smooth exit — orb releases, overlay fades — then emit.
  exiting.value = true
  phase.value = 'done'
  exitTimer = setTimeout(() => emit('complete'), EXIT_MS)
}

function skip() {
  cleanup()
  emit('skip')
}

function cleanup() {
  if (phaseTimer) clearTimeout(phaseTimer)
  if (exitTimer) clearTimeout(exitTimer)
  phaseTimer = null
  exitTimer = null
}

onMounted(() => {
  phaseTimer = setTimeout(nextPhase, PHASE_MS)
})

onUnmounted(cleanup)
</script>

<template>
  <Teleport to="body">
    <div :class="['breath-overlay', { 'breath-overlay--exiting': exiting }]" role="dialog" aria-label="Breathing exercise">
      <button
        @click="skip"
        class="breath-skip"
        aria-label="Skip breathing exercise"
      >
        <X :size="20" />
      </button>

      <div class="breath-stage">
        <!-- Orb: scale animation tied to phase via :class -->
        <div class="breath-orb" :class="`breath-orb--${phase}`">
          <div class="breath-orb__glow" />
          <div class="breath-orb__core" />
        </div>

        <!-- Phase label -->
        <div class="breath-label" :class="`breath-label--${phase}`">
          {{ phaseLabel }}
        </div>

        <!-- Cycle counter -->
        <div class="breath-cycle">{{ Math.min(cycle, CYCLES) }} of {{ CYCLES }}</div>
      </div>

      <!-- Progress bar at bottom — pure CSS animation, no JS tick.
           Eliminates the 50ms-interval reactive churn that was competing
           with the orb's CSS transition for main-thread time. -->
      <div class="breath-progress" aria-hidden="true">
        <div class="breath-progress__fill" :style="{ animationDuration: totalMs + 'ms' }" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.breath-overlay {
  position: fixed;
  inset: 0;
  z-index: 10001;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at center, rgba(20, 20, 35, 0.96) 0%, rgba(8, 8, 16, 0.99) 100%);
  backdrop-filter: blur(8px);
  animation: overlay-fade 480ms cubic-bezier(0.16, 1, 0.3, 1);
  /* Exit transitions — driven by .breath-overlay--exiting */
  transition:
    opacity 900ms cubic-bezier(0.32, 0.72, 0, 1),
    backdrop-filter 900ms cubic-bezier(0.32, 0.72, 0, 1),
    -webkit-backdrop-filter 900ms cubic-bezier(0.32, 0.72, 0, 1);
}

.breath-overlay--exiting {
  /* Override the entrance animation so opacity transition isn't fighting it */
  animation: none;
  opacity: 0;
  backdrop-filter: blur(0);
  -webkit-backdrop-filter: blur(0);
  pointer-events: none;
}

@keyframes overlay-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}

.breath-skip {
  position: absolute;
  top: max(1rem, env(safe-area-inset-top));
  right: max(1rem, env(safe-area-inset-right));
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.5);
  border-radius: 12px;
  cursor: pointer;
  transition: color 200ms, background 200ms, border-color 200ms;
}
.breath-skip:hover {
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
}

.breath-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rem;
}

/* ── Orb ────────────────────────────────────────────────────────── */
.breath-orb {
  position: relative;
  width: 200px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  /* Sine-like easing feels more natural for breathing than the default
     ease-in-out — slower at the peaks (held inhale/exhale), quicker
     through the transition. PHASE_MS in JS must match this duration.
     translate3d(0,0,0) forces GPU compositing without the cost of
     will-change on a bunch of static elements. */
  transition: transform 4s cubic-bezier(0.45, 0.05, 0.55, 0.95);
  transform: translate3d(0, 0, 0) scale(1);
}
.breath-orb--in  { transform: translate3d(0, 0, 0) scale(1); }
.breath-orb--out { transform: translate3d(0, 0, 0) scale(0.6); }
/* Final release — orb softly expands past 1 and dissolves */
.breath-orb--done {
  transform: translate3d(0, 0, 0) scale(1.45);
  opacity: 0;
  transition:
    transform 900ms cubic-bezier(0.16, 1, 0.3, 1),
    opacity 700ms cubic-bezier(0.4, 0, 0.2, 1);
}

.breath-orb__core {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%,
    rgba(168, 85, 247, 0.85) 0%,
    rgba(139, 92, 246, 0.55) 35%,
    rgba(124, 58, 237, 0.25) 70%,
    transparent 100%);
}

.breath-orb__glow {
  position: absolute;
  inset: -60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.18) 0%, transparent 70%);
  filter: blur(20px);
  pointer-events: none;
}

/* ── Label ──────────────────────────────────────────────────────── */
.breath-label {
  font-size: 1.5rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgba(241, 245, 249, 0.95);
  transition: opacity 600ms ease, transform 600ms ease;
}
.breath-label--in  { opacity: 1; transform: translateY(0); }
.breath-label--out { opacity: 0.85; transform: translateY(0); }
.breath-label--done { opacity: 0; transform: translateY(0); transition: opacity 600ms ease; }

.breath-cycle {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.4);
}

/* ── Progress ───────────────────────────────────────────────────── */
.breath-progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: max(0px, env(safe-area-inset-bottom));
  height: 2px;
  background: rgba(255, 255, 255, 0.05);
}
.breath-progress__fill {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, rgba(139, 92, 246, 0.6), rgba(168, 85, 247, 0.85));
  /* Single linear animation matching the total breath duration — no JS
     interval ticks. animation-duration is set inline by the parent. */
  animation: breath-progress-fill linear forwards;
  transform: translateZ(0);
}

@keyframes breath-progress-fill {
  from { width: 0; }
  to   { width: 100%; }
}

/* ── Reduced motion ─────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .breath-overlay { animation: none; }
  .breath-orb,
  .breath-label,
  .breath-progress__fill { transition: none !important; }
  .breath-orb--in,
  .breath-orb--out { transform: scale(0.85); }
}

/* ── Mobile sizing ──────────────────────────────────────────────── */
@media (max-width: 480px) {
  .breath-orb { width: 160px; height: 160px; }
  .breath-label { font-size: 1.25rem; }
}
</style>
