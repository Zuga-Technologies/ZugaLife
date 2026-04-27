/**
 * Shared state and utilities for ZugaLife tab components.
 *
 * Holds cross-tab concerns: gamification, celebration wiring,
 * billing modals, token notification, mood definitions, and
 * shared helpers.  Each tab component imports this composable
 * and gets the same reactive singleton.
 */

import { ref, computed } from 'vue'
import { api, ApiError, getToken } from '@core/api/client'
import { useCelebration } from './useCelebration'
import { useTokenStore } from '@core/billing/useTokens'
import { getMoods, type MoodDefinition } from '../mood-presets'
import { getActivePresetId, applyPreset } from '../theme-presets'

// ── Types ─────────────────────────────────────────────────────
export interface XPStatus {
  total_xp: number
  level: number
  level_name: string
  xp_for_next_level: number
  xp_progress_in_level: number
  current_streak_days: number
  longest_streak_days: number
  streak_multiplier: number
  prestige_level: number
  prestige_multiplier: number
  can_prestige: boolean
  streak_freezes: number
  streak_freeze_used: boolean
  bonus_label: string | null
  bonus_tier: string | null
  consistency_30d: number
  consistency_pct: number
}

export interface Badge {
  badge_key: string
  title: string
  description: string
  emoji: string
  earned_at: string | null
}

export interface DailyChallenge {
  challenge_key: string
  title: string
  description: string
  xp_reward: number
  is_completed: boolean
  is_ai_generated?: boolean
  goal_connection?: string | null
}

export interface WeeklyQuest {
  quest_key: string
  title: string
  description: string
  xp_reward: number
  is_completed: boolean
}

export interface GamificationData {
  xp: XPStatus
  badges: Badge[]
  recent_xp: Array<{ amount: number; source: string; description: string; created_at: string }>
  daily_challenges: DailyChallenge[]
  weekly_quests: WeeklyQuest[]
}

// ── Singleton state (shared across all tabs in the same component tree) ──
const gamificationData = ref<GamificationData | null>(null)
const activePresetId = ref(getActivePresetId())

// Billing modals
const showBillingPrompt = ref(false)
const billingPromptFeature = ref('')
const showBillingPacks = ref(false)
const tokenStore = useTokenStore()

// Service error modal
const showServiceError = ref(false)
const serviceErrorTitle = ref('')
const serviceErrorMessage = ref('')
const serviceErrorRetryFn = ref<(() => void) | null>(null)

// Meditation-ready toast — surfaces a clickable in-app banner when an
// extension-generated meditation finishes while the user is on another
// tab. Singleton so MeditateTab can set it from anywhere and LifeView
// renders it across all sub-tabs.
const pendingMeditationToast = ref<{ id: number; title: string } | null>(null)

// ── Static badge definitions ──
const STATIC_BADGES: Array<{ key: string; title: string; description: string }> = [
  { key: 'first_mood',       title: 'Mood Tracker',        description: 'Log your first mood' },
  { key: 'first_journal',    title: 'Dear Diary',          description: 'Write your first journal entry' },
  { key: 'first_meditation', title: 'Inner Peace',         description: 'Complete your first meditation' },
  { key: 'first_therapy',    title: 'Open Mind',           description: 'Start your first therapy session' },
  { key: 'streak_7',         title: 'Week Warrior',        description: '7-day activity streak' },
  { key: 'streak_30',        title: 'Monthly Master',      description: '30-day activity streak' },
  { key: 'streak_100',       title: 'Unstoppable',         description: '100-day activity streak' },
  { key: 'all_habits_day',   title: 'Perfect Day',         description: 'Complete all habits in one day' },
  { key: 'level_5',          title: 'Halfway There',       description: 'Reach level 5' },
  { key: 'level_10',         title: 'Enlightened',         description: 'Reach level 10' },
  { key: 'level_25',         title: 'Transcended',         description: 'Reach level 25' },
  { key: 'meditation_10',    title: 'Zen Master',          description: 'Complete 10 meditations' },
  { key: 'journal_10',       title: 'Storyteller',         description: 'Write 10 journal entries' },
  { key: 'mood_30',          title: 'Self Aware',          description: 'Log mood 30 times' },
  { key: 'goal_complete',    title: 'Goal Getter',         description: 'Complete your first goal' },
  { key: 'five_challenges',  title: 'Challenge Accepted',  description: 'Complete 5 daily challenges' },
]

const ALL_BADGES = computed(() => {
  const prestigeBadges: Array<{ key: string; title: string; description: string }> = []
  if (gamificationData.value) {
    for (const b of gamificationData.value.badges) {
      if (b.badge_key.startsWith('prestige_') && b.earned_at) {
        const tier = parseInt(b.badge_key.split('_')[1])
        const titles = ['First Ascension', 'Second Ascension', 'Third Ascension']
        prestigeBadges.push({
          key: b.badge_key,
          title: titles[tier - 1] || `Ascension ${tier}`,
          description: `Prestiged ${tier} time${tier > 1 ? 's' : ''}`,
        })
      }
    }
  }
  return [...STATIC_BADGES, ...prestigeBadges]
})

// ── Moods (driven by active theme preset) ──
const moods = computed(() => getMoods(activePresetId.value))

// ── Token conversion ──
const ZUGATOKENS_PER_DOLLAR = 100
const MARKUP_MULTIPLIER = 3

function costToTokens(usd: number): number {
  return Math.ceil(usd * MARKUP_MULTIPLIER * ZUGATOKENS_PER_DOLLAR)
}

function tokenLabel(usd: number): string {
  const n = costToTokens(usd)
  return n === 1 ? '1 token' : `${n} tokens`
}

function notifyTokenSpend() {
  window.dispatchEvent(new CustomEvent('zugatokens-updated'))
}

// ── Billing / error modals ──
function handleInsufficientTokens(feature: string): string {
  billingPromptFeature.value = feature
  showBillingPrompt.value = true
  showBillingPacks.value = false
  return 'You need more tokens to use this feature.'
}

function goToBilling() {
  showBillingPacks.value = true
  tokenStore.loadPacks()
}

function closeBillingPrompt() {
  showBillingPrompt.value = false
  showBillingPacks.value = false
}

function handleServiceError(title: string, message: string, retryFn?: () => void): string {
  serviceErrorTitle.value = title
  serviceErrorMessage.value = message
  serviceErrorRetryFn.value = retryFn ?? null
  showServiceError.value = true
  return message
}

function closeServiceError() {
  showServiceError.value = false
  serviceErrorRetryFn.value = null
}

function retryFromServiceError() {
  const fn = serviceErrorRetryFn.value
  closeServiceError()
  if (fn) fn()
}

// ── Gamification fetch ──
async function fetchGamification() {
  try {
    gamificationData.value = await api.get<GamificationData>('/api/life/gamification')
  } catch (e) {
    console.error('Gamification fetch failed:', e)
  }
}

// ── Helpers ──
function parseUTC(iso: string): Date {
  return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
}

function timeAgo(iso: string): string {
  const diff = Date.now() - parseUTC(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDate(iso: string): string {
  return parseUTC(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function formatDashboardDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  })
}

function formatDeadline(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const now = new Date()
  const diff = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diff < 0) return 'overdue'
  if (diff === 0) return 'today'
  if (diff === 1) return 'tomorrow'
  if (diff <= 7) return `${diff} days`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^## (.+)$/gm, '<h3 class="text-base font-semibold text-txt-primary mt-4 mb-1">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-surface-3 px-1 rounded text-xs">$1</code>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-sm text-txt-secondary">$1</li>')
    .replace(/(<li[^>]*>.*<\/li>\n?)+/g, (m) => `<ul class="my-2">${m}</ul>`)
    .replace(/\n/g, '<br>')
}

const emojiRe = /[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu
function stripEmoji(s: string): string {
  return s.replace(emojiRe, '').replace(/\s{2,}/g, ' ').trim()
}

// ── Celebration wrapper ──
const celebration = useCelebration()

// `withCelebration` is now a pass-through after gamification UI was retired
// 2026-04-26. The wrapper stays so call-sites (HabitsTab, JournalTab, etc.)
// don't need touching in this pass; it'll be removed when gamification is
// re-homed at the ZugaTokens platform layer.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function withCelebration<T>(action: () => Promise<T>, _source?: string): Promise<T> {
  return action()
}

// ── Export composable ──
export function useLifeShared() {
  return {
    // State
    gamificationData,
    activePresetId,
    moods,
    ALL_BADGES,
    celebration,

    // Billing
    showBillingPrompt,
    billingPromptFeature,
    showBillingPacks,
    tokenStore,
    handleInsufficientTokens,
    goToBilling,
    closeBillingPrompt,

    // Service error
    showServiceError,
    pendingMeditationToast,
    serviceErrorTitle,
    serviceErrorMessage,
    serviceErrorRetryFn,
    handleServiceError,
    closeServiceError,
    retryFromServiceError,

    // Gamification
    fetchGamification,
    withCelebration,
    costToTokens,
    tokenLabel,
    notifyTokenSpend,

    // Helpers
    parseUTC,
    timeAgo,
    formatDate,
    formatDashboardDate,
    formatDeadline,
    renderMarkdown,
    stripEmoji,
  }
}
