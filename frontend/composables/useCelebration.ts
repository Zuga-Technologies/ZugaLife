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
  type: 'xp' | 'streak' | 'challenge' | 'info' | 'bonus' | 'freeze'
  message: string
  xp?: number
  tier?: 'rare' | 'epic' | 'legendary'
  duration: number // ms
}

export interface BadgePopup {
  badge_key: string
  title: string
  description: string
}

export interface LevelUp {
  oldLevel: number
  newLevel: number
  newLevelName: string
}

export interface PrestigeUp {
  newPrestigeLevel: number
  prestigeMultiplier: number
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
let _lastActionSource: string | null = null

// ---------------------------------------------------------------------------
// Identity language — maps action sources to psychologically-grounded phrases
// (James Clear: "Every action is a vote for the type of person you want to become")
// ---------------------------------------------------------------------------

const IDENTITY_MESSAGES: Record<string, string[]> = {
  mood_log:             ['You checked in with yourself', 'You paused to notice how you feel'],
  habit_check:          ['You showed up for your health', 'You kept a promise to yourself'],
  journal_entry:        ['You processed your thoughts', 'You made sense of your day'],
  meditation_complete:  ['You chose presence over noise', 'You gave your mind space to breathe'],
  therapist_session:    ['You invested in your growth', 'You chose to understand yourself better'],
  goal_milestone:       ['You moved closer to who you want to be', 'You proved something to yourself'],
  daily_challenge:      ['You rose to the challenge', 'You pushed yourself today'],
}

function getIdentityMessage(source: string): string {
  const messages = IDENTITY_MESSAGES[source]
  if (!messages) return ''
  return messages[Math.floor(Math.random() * messages.length)]
}

function setActionSource(source: string) {
  _lastActionSource = source
}

/**
 * Compute an intrinsic benefit message from the action source and current XP data.
 * Shows the REAL reward (data-driven insight) alongside the game reward (XP).
 * Psychology: prevents overjustification by making the intrinsic benefit visible.
 */
function getIntrinsicBenefit(
  source: string,
  xpData: { consistency_30d?: number; consistency_pct?: number; current_streak_days: number },
): string | null {
  const consistency = xpData.consistency_30d ?? 0
  const streak = xpData.current_streak_days

  switch (source) {
    case 'meditation_complete':
      return consistency > 5
        ? `You've meditated ${consistency} of the last 30 days`
        : null
    case 'habit_check':
      return consistency > 7
        ? `${Math.round(xpData.consistency_pct ?? 0)}% consistency this month`
        : null
    case 'journal_entry':
      return streak > 3
        ? `${streak} days of showing up for yourself`
        : null
    case 'mood_log':
      return consistency > 3
        ? 'Tracking builds self-awareness \u2014 the foundation of change'
        : null
    case 'therapist_session':
      return 'Research: therapeutic alliance forms within 5 sessions'
    default:
      return null
  }
}

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

  // --- XP toast with identity language ---
  if (xpGained > 0) {
    const multiplierNote = newData.xp.streak_multiplier > 1
      ? ` (${newData.xp.streak_multiplier}x streak)`
      : ''
    const identity = _lastActionSource ? getIdentityMessage(_lastActionSource) : ''
    const identitySuffix = identity ? ` — ${identity}` : ''
    pushToast({
      type: 'xp',
      message: `+${xpGained} XP${multiplierNote}${identitySuffix}`,
      xp: xpGained,
      duration: identity ? 4000 : 3000, // Slightly longer when showing identity message
    })
  }

  // --- Intrinsic benefit toast (delayed, shows the REAL reward alongside XP) ---
  if (xpGained > 0 && _lastActionSource) {
    const benefit = getIntrinsicBenefit(_lastActionSource, newData.xp)
    if (benefit) {
      setTimeout(() => {
        pushToast({
          type: 'info',
          message: benefit,
          duration: 4500,
        })
      }, 1500)
    }
  }

  // --- Streak milestone toast (identity-framed) ---
  if (newData.xp.current_streak_days > oldSnap.current_streak_days) {
    const days = newData.xp.current_streak_days
    if ([7, 14, 21, 30, 50, 100].includes(days)) {
      const streakMessages: Record<number, string> = {
        7:   "A week of showing up — this is becoming who you are",
        14:  "Two weeks strong — your consistency is building something real",
        21:  "Three weeks — you're proving this isn't a phase",
        30:  "A full month — this is part of your identity now",
        50:  "50 days — you've rewired how you show up for yourself",
        100: "100 days — you are the living proof",
      }
      pushToast({
        type: 'streak',
        message: streakMessages[days] || `You've shown up ${days} days straight`,
        duration: 5000,
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
    }
    triggerConfetti()

    // Additional badges as toasts
    for (let i = 1; i < newBadges.length; i++) {
      const b = newBadges[i]
      pushToast({
        type: 'info',
        message: `Badge earned: ${b.title}`,
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

  // Clear snapshot and action source after processing
  _snapshot = null
  _lastActionSource = null
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
    badges: Array<{ badge_key: string; title: string; description: string; earned_at: string | null }>
  },
  allBadges: Array<{ key: string; title: string; description: string }>,
) {
  const titles = ['First Ascension', 'Second Ascension', 'Third Ascension']

  activePrestige.value = {
    newPrestigeLevel,
    prestigeMultiplier: 1.0 + newPrestigeLevel * 0.05,
    badgeTitle: titles[newPrestigeLevel - 1] || `Ascension ${newPrestigeLevel}`,
  }
  triggerConfetti(5000) // Longer confetti for prestige
  _snapshot = null
}

// ---------------------------------------------------------------------------
// Variable reward bonus celebration
// ---------------------------------------------------------------------------

function celebrateBonus(label: string, tier: 'rare' | 'epic' | 'legendary', xpGained: number) {
  pushToast({
    type: 'bonus',
    message: `${label} +${xpGained} XP`,
    xp: xpGained,
    tier,
    duration: tier === 'legendary' ? 5000 : 4000,
  })
  if (tier === 'legendary') {
    triggerConfetti(5000)
  } else if (tier === 'epic') {
    triggerConfetti(3000)
  }
}

// ---------------------------------------------------------------------------
// Streak freeze celebration
// ---------------------------------------------------------------------------

function celebrateFreezeSaved(streakDays: number) {
  pushToast({
    type: 'freeze',
    message: `Safety net kept your ${streakDays}-day momentum going 🧊→🔥`,
    duration: 5000,
  })
}

function celebrateStreakRecovery() {
  pushToast({
    type: 'info',
    message: 'Welcome back — you can pick up right where you left off',
    duration: 4000,
  })
}

function celebrateFreezeEarned(totalFreezes: number) {
  pushToast({
    type: 'info',
    message: `Streak Freeze earned! You have ${totalFreezes} safety net${totalFreezes > 1 ? 's' : ''} 🧊`,
    duration: 4000,
  })
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

    // Snapshot flow: call setActionSource + takeSnapshot BEFORE action, celebrateChanges AFTER re-fetch
    setActionSource,
    takeSnapshot,
    celebrateChanges,
    celebratePrestige,

    // Bonus & freeze celebrations
    celebrateBonus,
    celebrateFreezeSaved,
    celebrateFreezeEarned,
    celebrateStreakRecovery,
  }
}
