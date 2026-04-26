<script setup lang="ts">
import { computed } from 'vue'
import { useCelebration } from '../composables/useCelebration'
import { X, Trophy, Star, Zap, Flame, Sparkles, Snowflake } from 'lucide-vue-next'
import { badgeIcons, prestigeIcons } from '../icons'

// Map toast type to Lucide icon
const toastIcons: Record<string, any> = { xp: Zap, streak: Flame, challenge: Trophy, info: Star, bonus: Sparkles, freeze: Snowflake }

const {
  toasts,
  activeBadge,
  activeLevelUp,
  activePrestige,
  confettiActive,
  soundEnabled,
  dismissToast,
  dismissBadge,
  dismissLevelUp,
  dismissPrestige,
} = useCelebration()

// Generate confetti particles (deterministic, no randomness at render time)
const confettiParticles = Array.from({ length: 50 }, (_, i) => ({
  id: i,
  color: ['#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#22c55e', '#f97316', '#ec4899'][i % 7],
  left: `${(i * 17 + 3) % 100}%`,
  delay: `${(i * 0.06).toFixed(2)}s`,
  size: i % 3 === 0 ? 10 : i % 3 === 1 ? 7 : 5,
  drift: i % 2 === 0 ? 1 : -1,
}))

// Level names for display
const levelNames: Record<number, string> = {
  1: 'Beginner', 2: 'Explorer', 3: 'Seeker', 4: 'Practitioner', 5: 'Achiever',
  6: 'Dedicated', 7: 'Mindful', 8: 'Resilient', 9: 'Master', 10: 'Enlightened',
  11: 'Awakened', 12: 'Focused', 13: 'Disciplined', 14: 'Empowered', 15: 'Transcendent',
  16: 'Harmonious', 17: 'Luminous', 18: 'Sovereign', 19: 'Ascendant', 20: 'Legendary',
  21: 'Mythic', 22: 'Eternal', 23: 'Celestial', 24: 'Divine', 25: 'Transcended',
}
</script>

<template>
  <!-- Toast Stack — bottom-right desktop, top-center mobile -->
  <Teleport to="body">
    <div class="cel-toast-stack" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="cel-toast"
          :class="`cel-toast--${toast.type}`"
          @click="dismissToast(toast.id)"
          role="status"
        >
          <component v-if="toastIcons[toast.type]" :is="toastIcons[toast.type]" :size="18" class="cel-toast__icon" />
          <span class="cel-toast__msg">{{ toast.message }}</span>
          <span v-if="toast.tier" class="cel-toast__tier" :class="`cel-toast__tier--${toast.tier}`">{{ toast.tier }}</span>
        </div>
      </TransitionGroup>
    </div>

    <!-- Confetti Layer -->
    <Transition name="confetti-fade">
      <div v-if="confettiActive" class="cel-confetti" aria-hidden="true">
        <div
          v-for="p in confettiParticles"
          :key="p.id"
          class="cel-confetti__particle"
          :style="{
            left: p.left,
            animationDelay: p.delay,
            backgroundColor: p.color,
            width: p.size + 'px',
            height: p.size + 'px',
            '--drift': p.drift,
          }"
        />
      </div>
    </Transition>

    <!-- Badge Earned Modal -->
    <Transition name="modal">
      <div v-if="activeBadge" class="cel-modal-overlay" @click.self="dismissBadge">
        <div class="cel-modal cel-modal--badge">
          <button class="cel-modal__close" @click="dismissBadge" aria-label="Close">
            <X :size="18" />
          </button>
          <div class="cel-modal__shine" />
          <div class="cel-badge-icon">
            <component v-if="badgeIcons[activeBadge.badge_key]" :is="badgeIcons[activeBadge.badge_key]" :size="48" class="text-accent-alt" />
          </div>
          <div class="cel-modal__label">You've proven something</div>
          <div class="cel-modal__title">{{ activeBadge.title }}</div>
          <div class="cel-modal__desc">{{ activeBadge.description }}</div>
          <button class="cel-modal__btn" @click="dismissBadge">That's who I am</button>
        </div>
      </div>
    </Transition>

    <!-- Level Up Modal -->
    <Transition name="modal">
      <div v-if="activeLevelUp" class="cel-modal-overlay" @click.self="dismissLevelUp">
        <div class="cel-modal cel-modal--levelup">
          <button class="cel-modal__close" @click="dismissLevelUp" aria-label="Close">
            <X :size="18" />
          </button>
          <div class="cel-modal__shine cel-modal__shine--gold" />
          <div class="cel-levelup-stars">
            <Star :size="20" class="cel-star cel-star--1" />
            <Star :size="28" class="cel-star cel-star--2" />
            <Star :size="20" class="cel-star cel-star--3" />
          </div>
          <div class="cel-levelup-number">{{ activeLevelUp.newLevel }}</div>
          <div class="cel-modal__label">Level Up!</div>
          <div class="cel-modal__title">{{ activeLevelUp.newLevelName }}</div>
          <div class="cel-modal__desc">
            Your consistency is building something real — Level {{ activeLevelUp.newLevel }}
          </div>
          <button class="cel-modal__btn cel-modal__btn--gold" @click="dismissLevelUp">Onward</button>
        </div>
      </div>
    </Transition>

    <!-- Prestige Modal -->
    <Transition name="modal">
      <div v-if="activePrestige" class="cel-modal-overlay" @click.self="dismissPrestige">
        <div class="cel-modal cel-modal--prestige">
          <button class="cel-modal__close" @click="dismissPrestige" aria-label="Close">
            <X :size="18" />
          </button>
          <div class="cel-modal__shine cel-modal__shine--prestige" />
          <div class="cel-prestige-badge">
            <component :is="prestigeIcons[(activePrestige.newPrestigeLevel - 1) % prestigeIcons.length]" :size="56" class="text-accent-alt" />
          </div>
          <div class="cel-prestige-tier">Prestige {{ activePrestige.newPrestigeLevel }}</div>
          <div class="cel-modal__label cel-modal__label--prestige">Ascension Complete</div>
          <div class="cel-modal__title">{{ activePrestige.badgeTitle }}</div>
          <div class="cel-modal__desc">
            Permanent +{{ Math.round((activePrestige.prestigeMultiplier - 1) * 100) }}% XP bonus active
          </div>
          <button class="cel-modal__btn cel-modal__btn--prestige" @click="dismissPrestige">Onward!</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ================================================================
   MOTION TOKENS — single source of truth for all celebrations.
   Use --ease-smooth (quart-out) for entrances, --ease-exit for leaves.
   Durations are slightly tiered: fast (toast), base (modal), slow (hero).
   ================================================================ */
.cel-toast-stack,
.cel-modal-overlay,
.cel-confetti {
  --ease-smooth: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-exit:   cubic-bezier(0.4, 0, 0.6, 1);
  --dur-fast:   220ms;
  --dur-base:   360ms;
  --dur-slow:   520ms;
}

/* ================================================================
   TOAST STACK
   Desktop: bottom-right. Mobile: top-center.
   ================================================================ */
.cel-toast-stack {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  z-index: 9999;
  display: flex;
  flex-direction: column-reverse;
  gap: 0.5rem;
  pointer-events: none;
  max-width: 340px;
}

@media (max-width: 640px) {
  .cel-toast-stack {
    bottom: auto;
    top: 1rem;
    right: 1rem;
    left: 1rem;
    max-width: none;
    align-items: center;
  }
}

.cel-toast {
  pointer-events: auto;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  border-radius: 0.75rem;
  background: rgba(15, 15, 25, 0.92);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  color: #e2e8f0;
  font-size: 0.875rem;
  font-weight: 600;
  min-height: 44px; /* touch target */
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.cel-toast--xp {
  border-color: rgba(245, 158, 11, 0.3);
  background: linear-gradient(135deg, rgba(15, 15, 25, 0.92) 0%, rgba(245, 158, 11, 0.08) 100%);
}

.cel-toast--streak {
  border-color: rgba(239, 68, 68, 0.3);
  background: linear-gradient(135deg, rgba(15, 15, 25, 0.92) 0%, rgba(239, 68, 68, 0.08) 100%);
}

.cel-toast--challenge {
  border-color: rgba(34, 197, 94, 0.3);
  background: linear-gradient(135deg, rgba(15, 15, 25, 0.92) 0%, rgba(34, 197, 94, 0.08) 100%);
}

.cel-toast__icon {
  flex-shrink: 0;
  color: currentColor;
}

.cel-toast--xp .cel-toast__icon { color: #f59e0b; }
.cel-toast--streak .cel-toast__icon { color: #ef4444; }
.cel-toast--challenge .cel-toast__icon { color: #22c55e; }
.cel-toast--info .cel-toast__icon { color: #8b5cf6; }

/* Variable reward bonus toasts */
.cel-toast--bonus {
  border-color: rgba(234, 179, 8, 0.5);
  background: linear-gradient(135deg, rgba(15, 15, 25, 0.92) 0%, rgba(234, 179, 8, 0.15) 100%);
  animation: bonus-shimmer 1.5s ease-in-out infinite;
}
.cel-toast--bonus .cel-toast__icon { color: #eab308; }

/* Streak freeze toast */
.cel-toast--freeze {
  border-color: rgba(6, 182, 212, 0.4);
  background: linear-gradient(135deg, rgba(15, 15, 25, 0.92) 0%, rgba(6, 182, 212, 0.12) 100%);
}
.cel-toast--freeze .cel-toast__icon { color: #06b6d4; }

@keyframes bonus-shimmer {
  0%, 100% { box-shadow: 0 0 8px rgba(234, 179, 8, 0.2); }
  50% { box-shadow: 0 0 20px rgba(234, 179, 8, 0.4); }
}

.cel-toast__tier {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.cel-toast__tier--rare { background: rgba(234, 179, 8, 0.2); color: #eab308; }
.cel-toast__tier--epic { background: rgba(168, 85, 247, 0.2); color: #a855f7; }
.cel-toast__tier--legendary { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

.cel-toast__msg {
  flex: 1;
}

/* Toast enter/leave — smooth quart-out, no overshoot.
   Subtle slide + fade only; scale stays at 1 so the toast doesn't pulse. */
.toast-enter-active {
  animation: toast-in var(--dur-fast) var(--ease-smooth);
}
.toast-leave-active {
  animation: toast-out var(--dur-fast) var(--ease-exit);
}
.toast-move {
  transition: transform var(--dur-fast) var(--ease-smooth);
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateX(24px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes toast-out {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(24px);
  }
}

@media (max-width: 640px) {
  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateY(-16px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  @keyframes toast-out {
    from {
      opacity: 1;
      transform: translateY(0);
    }
    to {
      opacity: 0;
      transform: translateY(-16px);
    }
  }
}

/* ================================================================
   CONFETTI
   Pure CSS particles — GPU-accelerated transforms only
   ================================================================ */
.cel-confetti {
  position: fixed;
  inset: 0;
  z-index: 9998;
  pointer-events: none;
  overflow: hidden;
}

.cel-confetti__particle {
  position: absolute;
  top: -12px;
  border-radius: 2px;
  animation: confetti-fall 3s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
  will-change: transform, opacity;
}

@keyframes confetti-fall {
  0% {
    transform: translateY(0) rotate(0deg) scale(1);
    opacity: 1;
  }
  25% {
    transform: translateY(25vh) rotate(180deg) translateX(calc(var(--drift, 1) * 30px)) scale(1);
    opacity: 1;
  }
  75% {
    opacity: 0.7;
  }
  100% {
    transform: translateY(105vh) rotate(720deg) translateX(calc(var(--drift, 1) * 60px)) scale(0.5);
    opacity: 0;
  }
}

.confetti-fade-leave-active {
  transition: opacity 0.5s ease;
}
.confetti-fade-leave-to {
  opacity: 0;
}

/* ================================================================
   MODAL OVERLAY & SHARED MODAL STYLES
   ================================================================ */
.cel-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  padding: 1rem;
  -webkit-tap-highlight-color: transparent;
}

.cel-modal {
  position: relative;
  width: 100%;
  max-width: 320px;
  border-radius: 1.25rem;
  padding: 2rem 1.5rem 1.5rem;
  text-align: center;
  overflow: hidden;
  background: rgba(20, 20, 35, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 40px rgba(139, 92, 246, 0.15);
}

.cel-modal__close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  padding: 0.25rem;
  min-width: 44px;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  transition: color 0.2s;
}

.cel-modal__close:hover {
  color: rgba(255, 255, 255, 0.8);
}

.cel-modal__shine {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(ellipse at center, rgba(139, 92, 246, 0.15) 0%, transparent 60%);
  animation: shine-pulse 2s ease-in-out infinite;
  pointer-events: none;
}

.cel-modal__shine--gold {
  background: radial-gradient(ellipse at center, rgba(245, 158, 11, 0.2) 0%, transparent 60%);
}

@keyframes shine-pulse {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.05); }
}

.cel-modal__label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: rgba(139, 92, 246, 0.8);
  margin-bottom: 0.25rem;
}

.cel-modal--levelup .cel-modal__label {
  color: rgba(245, 158, 11, 0.9);
}

.cel-modal__title {
  font-size: 1.5rem;
  font-weight: 800;
  color: #f1f5f9;
  margin-bottom: 0.5rem;
}

.cel-modal__desc {
  font-size: 0.875rem;
  color: rgba(226, 232, 240, 0.6);
  line-height: 1.4;
  margin-bottom: 1.25rem;
}

.cel-modal__btn {
  width: 100%;
  padding: 0.75rem;
  border: none;
  border-radius: 0.75rem;
  font-size: 0.9375rem;
  font-weight: 700;
  cursor: pointer;
  min-height: 44px;
  transition: transform 0.15s, box-shadow 0.15s;
  background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
}

.cel-modal__btn:active {
  transform: scale(0.97);
}

.cel-modal__btn--gold {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

/* ================================================================
   BADGE MODAL SPECIFICS
   ================================================================ */
.cel-badge-icon {
  display: flex;
  justify-content: center;
  font-size: 3.5rem;
  margin-bottom: 0.75rem;
  /* Entrance is handled by .cel-modal > * content-up stagger.
     Keep a subtle ambient breath so the icon feels alive after entry. */
  animation: badge-breath 4s ease-in-out 600ms infinite;
}

@keyframes badge-breath {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.04); }
}

/* ================================================================
   LEVEL UP MODAL SPECIFICS
   ================================================================ */
.cel-levelup-stars {
  display: flex;
  justify-content: center;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
  color: #f59e0b;
}

/* Stars enter with the content stagger; keep only a gentle twinkle after. */
.cel-star {
  animation: star-twinkle 2.4s ease-in-out infinite;
}
.cel-star--1 { animation-delay: 0s; }
.cel-star--2 { animation-delay: 0.4s; }
.cel-star--3 { animation-delay: 0.8s; }

@keyframes star-twinkle {
  0%, 100% { opacity: 0.85; transform: scale(1); }
  50%      { opacity: 1;    transform: scale(1.08); }
}

.cel-levelup-number {
  font-size: 3rem;
  font-weight: 900;
  background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 50%, #f59e0b 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 2s ease-in-out infinite;
  margin-bottom: 0.25rem;
}

@keyframes shimmer {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

/* ================================================================
   MODAL TRANSITIONS — overlay fades, modal does ONE smooth scale-up
   from 0.94 (not 0.7), and inner content staggers in slightly delayed
   so the icon/title don't fight the container scale.
   ================================================================ */
.modal-enter-active {
  animation: overlay-fade var(--dur-fast) var(--ease-smooth);
}
.modal-leave-active {
  animation: overlay-fade var(--dur-fast) var(--ease-exit) reverse;
}

.modal-enter-active .cel-modal {
  animation: modal-in var(--dur-base) var(--ease-smooth);
}
.modal-leave-active .cel-modal {
  animation: modal-out var(--dur-fast) var(--ease-exit);
}

@keyframes overlay-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes modal-in {
  from {
    opacity: 0;
    transform: scale(0.94) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

@keyframes modal-out {
  from {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
  to {
    opacity: 0;
    transform: scale(0.96) translateY(4px);
  }
}

/* Content stagger inside modal — runs AFTER modal scale settles.
   Tiny offsets so it reads as one breath, not separate items popping. */
.cel-modal > * {
  animation: content-up var(--dur-base) var(--ease-smooth) both;
}
.cel-modal > *:nth-child(2) { animation-delay: 80ms; }
.cel-modal > *:nth-child(3) { animation-delay: 110ms; }
.cel-modal > *:nth-child(4) { animation-delay: 140ms; }
.cel-modal > *:nth-child(5) { animation-delay: 170ms; }
.cel-modal > *:nth-child(6) { animation-delay: 200ms; }
.cel-modal > *:nth-child(7) { animation-delay: 230ms; }
/* Close button + shine layer should not stagger — keep them as-is */
.cel-modal > .cel-modal__close,
.cel-modal > .cel-modal__shine {
  animation: none;
}

@keyframes content-up {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ================================================================
   PRESTIGE MODAL SPECIFICS
   ================================================================ */
.cel-modal--prestige {
  border-color: rgba(168, 85, 247, 0.3);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 60px rgba(168, 85, 247, 0.2), 0 0 30px rgba(245, 158, 11, 0.1);
}

.cel-modal__shine--prestige {
  background: radial-gradient(ellipse at center, rgba(168, 85, 247, 0.25) 0%, rgba(245, 158, 11, 0.1) 40%, transparent 65%);
  animation: prestige-shine 2.5s ease-in-out infinite;
}

@keyframes prestige-shine {
  0%, 100% { opacity: 0.5; transform: scale(1) rotate(0deg); }
  50% { opacity: 1; transform: scale(1.1) rotate(3deg); }
}

.cel-modal__label--prestige {
  color: rgba(168, 85, 247, 0.9);
}

.cel-prestige-badge {
  font-size: 4.5rem;
  margin-bottom: 0.5rem;
  /* Entrance via content-up stagger; keep a slow ambient breath for hero feel. */
  animation: badge-breath 4s ease-in-out 700ms infinite;
  filter: drop-shadow(0 0 12px rgba(168, 85, 247, 0.4));
}

.cel-prestige-tier {
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  background: linear-gradient(135deg, #a855f7 0%, #f59e0b 50%, #a855f7 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 2s ease-in-out infinite;
  margin-bottom: 0.5rem;
}

.cel-modal__btn--prestige {
  background: linear-gradient(135deg, #7c3aed 0%, #a855f7 50%, #f59e0b 100%);
  box-shadow: 0 4px 16px rgba(168, 85, 247, 0.4);
}

/* Respect reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  .cel-confetti__particle,
  .cel-badge-icon,
  .cel-star,
  .cel-levelup-number,
  .cel-prestige-badge,
  .cel-prestige-tier,
  .cel-modal__shine,
  .cel-toast--bonus,
  .cel-modal > * {
    animation: none !important;
  }
  .modal-enter-active,
  .modal-leave-active,
  .toast-enter-active,
  .toast-leave-active,
  .modal-enter-active .cel-modal,
  .modal-leave-active .cel-modal {
    animation: none !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
