/**
 * useCelebration — Reactive celebration state for ZugaLife gamification feedback.
 *
 * Singleton pattern: all components share the same reactive state.
 * Mobile-ready: no DOM manipulation, just reactive data that drives CSS animations.
 */
import { ref, reactive } from 'vue'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Toast {
  id: number
  type: 'xp' | 'streak' | 'challenge' | 'info'
  message: string
  xp?: number
  icon?: string
  duration: number // ms
}

export interface BadgePopup {
  badge_key: string
  title: string
  description: string
  emoji: string
}

export interface LevelUp {
  oldLevel: number
  newLevel: number
  newLevelName: string
}

export interface PrestigeUp {
  newPrestigeLevel: number
  prestigeMultiplier: number
  badgeEmoji: string
  badgeTitle: string
}

export interface GamificationSnapshot {
  total_xp: number
  level: number
  level_name: string
  current_streak_days: number
  streak_multiplier: number
  badge_keys: string[]
}

// ---------------------------------------------------------------------------
// Singleton state (shared across all component instances)
// ---------------------------------------------------------------------------

const toasts = reactive<Toast[]>([])
const activeBadge = ref<BadgePopup | null>(null)
const activeLevelUp = ref<LevelUp | null>(null)
const activePrestige = ref<PrestigeUp | null>(null)
const confettiActive = ref(false)
const soundEnabled = ref(true)

let _toastId = 0
let _snapshot: GamificationSnapshot | null = null

// ---------------------------------------------------------------------------
// Toast management
// ---------------------------------------------------------------------------

function pushToast(toast: Omit<Toast, 'id'>) {
  const id = ++_toastId
  const entry: Toast = { ...toast, id }
  toasts.push(entry)

  // Auto-dismiss
  setTimeout(() => {
    const idx = toasts.findIndex(t => t.id === id)
    if (idx !== -1) toasts.splice(idx, 1)
  }, toast.duration)

  return id
}

function dismissToast(id: number) {
  const idx = toasts.findIndex(t => t.id === id)
  if (idx !== -1) toasts.splice(idx, 1)
}

// ---------------------------------------------------------------------------
// Snapshot & diff — detect what changed after an XP-awarding action
// ---------------------------------------------------------------------------

function takeSnapshot(gamData: {
  xp: { total_xp: number; level: number; level_name: string; current_streak_days: number; streak_multiplier: number }
  badges: Array<{ badge_key: string; earned_at: string | null }>
}) {
  _snapshot = {
    total_xp: gamData.xp.total_xp,
    level: gamData.xp.level,
    level_name: gamData.xp.level_name,
    current_streak_days: gamData.xp.current_streak_days,
    streak_multiplier: gamData.xp.streak_multiplier,
    badge_keys: gamData.badges.filter(b => b.earned_at).map(b => b.badge_key),
  }
}

function celebrateChanges(
  newData: {
    xp: { total_xp: number; level: number; level_name: string; current_streak_days: number; streak_multiplier: number }
    badges: Array<{ badge_key: string; title: string; description: string; emoji: string; earned_at: string | null }>
  },
  allBadges: Array<{ key: string; title: string; emoji: string; description: string }>,
) {
  if (!_snapshot) return

  const oldSnap = _snapshot
  const xpGained = newData.xp.total_xp - oldSnap.total_xp

  // --- XP toast ---
  if (xpGained > 0) {
    const multiplierNote = newData.xp.streak_multiplier > 1
      ? ` (${newData.xp.streak_multiplier}x streak)`
      : ''
    pushToast({
      type: 'xp',
      message: `+${xpGained} XP${multiplierNote}`,
      xp: xpGained,
      icon: '⚡',
      duration: 3000,
    })
  }

  // --- Streak milestone toast ---
  if (newData.xp.current_streak_days > oldSnap.current_streak_days) {
    const days = newData.xp.current_streak_days
    // Only celebrate milestone streaks (7, 14, 21, 30, 50, 100)
    if ([7, 14, 21, 30, 50, 100].includes(days)) {
      pushToast({
        type: 'streak',
        message: `${days}-day streak!`,
        icon: '🔥',
        duration: 4000,
      })
    }
  }

  // --- New badges ---
  const oldBadgeSet = new Set(oldSnap.badge_keys)
  const newBadges = newData.badges
    .filter(b => b.earned_at && !oldBadgeSet.has(b.badge_key))

  if (newBadges.length > 0) {
    // Show the first new badge as a popup (queue the rest as toasts)
    const first = newBadges[0]
    activeBadge.value = {
      badge_key: first.badge_key,
      title: first.title,
      description: first.description,
      emoji: first.emoji,
    }
    triggerConfetti()

    // Additional badges as toasts
    for (let i = 1; i < newBadges.length; i++) {
      const b = newBadges[i]
      pushToast({
        type: 'info',
        message: `Badge earned: ${b.title}`,
        icon: b.emoji,
        duration: 4000,
      })
    }
  }

  // --- Level up ---
  if (newData.xp.level > oldSnap.level) {
    activeLevelUp.value = {
      oldLevel: oldSnap.level,
      newLevel: newData.xp.level,
      newLevelName: newData.xp.level_name,
    }
    triggerConfetti()
  }

  // Clear snapshot after processing
  _snapshot = null
}

// ---------------------------------------------------------------------------
// Confetti control
// ---------------------------------------------------------------------------

function triggerConfetti(durationMs = 3000) {
  confettiActive.value = true
  setTimeout(() => { confettiActive.value = false }, durationMs)
}

// ---------------------------------------------------------------------------
// Badge / Level-up dismiss
// ---------------------------------------------------------------------------

function dismissBadge() {
  activeBadge.value = null
}

function dismissLevelUp() {
  activeLevelUp.value = null
}

function dismissPrestige() {
  activePrestige.value = null
}

function celebratePrestige(
  newPrestigeLevel: number,
  newData: {
    xp: { total_xp: number; level: number; level_name: string; current_streak_days: number; streak_multiplier: number; prestige_level: number; prestige_multiplier: number }
    badges: Array<{ badge_key: string; title: string; description: string; emoji: string; earned_at: string | null }>
  },
  allBadges: Array<{ key: string; title: string; emoji: string; description: string }>,
) {
  const prestigeEmojis = ['🌟', '💫', '✨', '🔱', '👑', '💎', '🌠', '🏅']
  const titles = ['First Ascension', 'Second Ascension', 'Third Ascension']

  activePrestige.value = {
    newPrestigeLevel,
    prestigeMultiplier: 1.0 + newPrestigeLevel * 0.05,
    badgeEmoji: prestigeEmojis[(newPrestigeLevel - 1) % prestigeEmojis.length],
    badgeTitle: titles[newPrestigeLevel - 1] || `Ascension ${newPrestigeLevel}`,
  }
  triggerConfetti(5000) // Longer confetti for prestige
  _snapshot = null
}

// ---------------------------------------------------------------------------
// Sound toggle (persisted via localStorage)
// ---------------------------------------------------------------------------

const SOUND_KEY = 'zugalife-celebration-sounds'

function initSoundPref() {
  const stored = localStorage.getItem(SOUND_KEY)
  if (stored !== null) soundEnabled.value = stored === '1'
}

function toggleSound() {
  soundEnabled.value = !soundEnabled.value
  localStorage.setItem(SOUND_KEY, soundEnabled.value ? '1' : '0')
}

// ---------------------------------------------------------------------------
// Composable export
// ---------------------------------------------------------------------------

export function useCelebration() {
  initSoundPref()

  return {
    // Reactive state (read-only from components)
    toasts,
    activeBadge,
    activeLevelUp,
    activePrestige,
    confettiActive,
    soundEnabled,

    // Actions
    pushToast,
    dismissToast,
    dismissBadge,
    dismissLevelUp,
    dismissPrestige,
    triggerConfetti,
    toggleSound,

    // Snapshot flow: call takeSnapshot BEFORE action, celebrateChanges AFTER re-fetch
    takeSnapshot,
    celebrateChanges,
    celebratePrestige,
  }
}
