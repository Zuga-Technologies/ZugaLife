<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api, ApiError, getToken } from '@core/api/client'
import { startAmbience, stopAmbience, pauseAmbience, resumeAmbience, setAmbienceVolume } from './ambience'
import { moodIcons, meditationTypeIcons, ambienceIcons, habitIcons, habitIconPicker, habitIconCategories, badgeIcons, xpSourceIcons, prestigeIcons, getIcon, BrandIcon } from './icons'
import {
  BookOpen, MessageCircleHeart, ScrollText, Send, Trash2, Pencil, X, AlertTriangle,
  LayoutDashboard, TrendingUp, Target, Clock, CalendarDays, ArrowRight, ArrowLeft,
  ChevronRight, ChevronDown, ChevronUp, Activity, Flame as FlameIcon, Brain as BrainIcon, Settings,
  Download, Trophy, Star, Zap, CheckCircle2, Lock, CircleDot, Meh,
} from 'lucide-vue-next'
import SettingsPanel from './SettingsPanel.vue'
import BackgroundTheme from './BackgroundTheme.vue'
import AnalyticsDashboard from './AnalyticsDashboard.vue'
import CelebrationOverlay from './components/CelebrationOverlay.vue'
import { useCelebration } from './composables/useCelebration'
import { playXpSound, playBadgeSound, playLevelUpSound, playStreakSound, playPrestigeSound } from './composables/useCelebrationSounds'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

// --- Settings ---
const showSettings = ref(false)

// --- Celebration System ---
const celebration = useCelebration()

/**
 * Wrap any XP-awarding action: snapshot before, re-fetch after, celebrate diff.
 * Usage: await withCelebration(() => api.post('/api/life/mood', { ... }))
 */
async function withCelebration<T>(action: () => Promise<T>): Promise<T> {
  if (gamificationData.value) {
    celebration.takeSnapshot(gamificationData.value)
  }
  const result = await action()
  // Re-fetch gamification data and celebrate changes
  try {
    const newData = await api.get<GamificationData>('/api/life/gamification')
    if (gamificationData.value) {
      celebration.celebrateChanges(newData, ALL_BADGES.value)
      // Play sounds based on what changed
      if (celebration.soundEnabled.value) {
        if (celebration.activeLevelUp.value) playLevelUpSound()
        else if (celebration.activeBadge.value) playBadgeSound()
        else if (newData.xp.total_xp !== (gamificationData.value?.xp.total_xp ?? 0)) playXpSound()
      }
    }
    gamificationData.value = newData
  } catch { /* gamification fetch is non-critical */ }
  return result
}

// --- Tabs ---

type Tab = 'dashboard' | 'journal' | 'habits' | 'goals' | 'meditate' | 'therapist'
const activeTab = ref<Tab>('dashboard')

// ============================
// DASHBOARD
// ============================

interface DashboardMoodEntry {
  emoji: string
  label: string
  date: string
}

interface DashboardHabitStat {
  name: string
  emoji: string
  completed: number
  total: number
}

interface DashboardData {
  greeting: string
  date: string
  mood: {
    recent: DashboardMoodEntry[]
    total: number
    has_data: boolean
  }
  habits: {
    has_data: boolean
    active_count: number
    completed: number
    total_possible: number
    completion_rate: number
    top_habits: DashboardHabitStat[]
  }
  goals: {
    has_data: boolean
    active: number
    completed: number
    nearest_deadline: { title: string; date: string } | null
    milestones_done: number
    milestones_total: number
  }
  meditation: {
    has_data: boolean
    sessions_this_week: number
    total_minutes: number
    avg_minutes: number
    total_sessions: number
  }
  journal: {
    has_data: boolean
    entries_this_week: number
    total: number
    latest_title: string | null
    latest_date: string | null
  }
  therapist: {
    has_data: boolean
    total_sessions: number
    last_date: string | null
    last_themes: string | null
    last_mood: string | null
  }
}

const dashboardData = ref<DashboardData | null>(null)
const loadingDashboard = ref(true)

async function fetchDashboard() {
  try {
    const res = await api.get<DashboardData>('/api/life/dashboard')
    dashboardData.value = res
  } catch (e) {
    console.error('Dashboard fetch failed:', e)
  }
}

// ============================
// GAMIFICATION
// ============================

interface XPStatus {
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
}

interface Badge {
  badge_key: string
  title: string
  description: string
  emoji: string
  earned_at: string | null
}

interface DailyChallenge {
  challenge_key: string
  title: string
  description: string
  xp_reward: number
  is_completed: boolean
  is_ai_generated?: boolean
}

interface WeeklyQuest {
  quest_key: string
  title: string
  description: string
  xp_reward: number
  is_completed: boolean
}

interface GamificationData {
  xp: XPStatus
  badges: Badge[]
  recent_xp: Array<{ amount: number; source: string; description: string; created_at: string }>
  daily_challenges: DailyChallenge[]
  weekly_quests: WeeklyQuest[]
}

const gamificationData = ref<GamificationData | null>(null)

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

// Dynamically include earned prestige badges in the display list
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

// Prestige action
const prestigeLoading = ref(false)
async function doPrestige() {
  if (!gamificationData.value?.xp.can_prestige || prestigeLoading.value) return
  prestigeLoading.value = true
  try {
    if (gamificationData.value) {
      celebration.takeSnapshot(gamificationData.value)
    }
    await api.post('/api/life/gamification/prestige')
    const newData = await api.get<GamificationData>('/api/life/gamification')
    if (gamificationData.value) {
      celebration.celebratePrestige(
        gamificationData.value.xp.prestige_level + 1,
        newData,
        ALL_BADGES.value,
      )
      if (celebration.soundEnabled.value) playPrestigeSound()
    }
    gamificationData.value = newData
  } catch (e: any) {
    console.error('Prestige failed:', e)
  } finally {
    prestigeLoading.value = false
  }
}

async function fetchGamification() {
  try {
    gamificationData.value = await api.get<GamificationData>('/api/life/gamification')
  } catch (e) {
    console.error('Gamification fetch failed:', e)
  }
}

// --- Therapist session navigation guard ---
const showTherapistLeaveWarning = ref(false)
const pendingTab = ref<Tab | null>(null)
const pendingRouteLeave = ref<(() => void) | null>(null)

function navigateTo(tab: Tab) {
  if (tab !== 'therapist' && therapistSessionActive.value && therapistMessages.value.length >= 2) {
    pendingTab.value = tab
    pendingRouteLeave.value = null
    showTherapistLeaveWarning.value = true
    return
  }
  activeTab.value = tab
}

function confirmTherapistLeave() {
  showTherapistLeaveWarning.value = false
  therapistSessionActive.value = false
  therapistMessages.value = []
  if (pendingTab.value) {
    activeTab.value = pendingTab.value
    pendingTab.value = null
  }
  if (pendingRouteLeave.value) {
    pendingRouteLeave.value()
    pendingRouteLeave.value = null
  }
}

function cancelTherapistLeave() {
  showTherapistLeaveWarning.value = false
  pendingTab.value = null
  pendingRouteLeave.value = null
}

// Guard: leaving ZugaLife entirely (router navigation to another studio)
onBeforeRouteLeave((_to, _from, next) => {
  if (therapistSessionActive.value && therapistMessages.value.length >= 2) {
    pendingTab.value = null
    pendingRouteLeave.value = () => next()
    showTherapistLeaveWarning.value = true
    next(false) // block navigation until user confirms
  } else {
    next()
  }
})

// Guard: browser refresh / close tab
function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (therapistSessionActive.value && therapistMessages.value.length >= 2) {
    e.preventDefault()
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnloadHandler))

// Dashboard mood picker
const dashMoodNote = ref('')
const dashMoodSubmitting = ref(false)
const dashMoodSuccess = ref<string | null>(null)
const dashMoodError = ref<string | null>(null)
const dashMoodCooldownUntil = ref<string | null>(null)

const dashMoodOnCooldown = computed(() => {
  if (!dashMoodCooldownUntil.value) return false
  return new Date(dashMoodCooldownUntil.value) > new Date()
})

const dashMoodTimeLeft = computed(() => {
  if (!dashMoodCooldownUntil.value) return ''
  const diff = new Date(dashMoodCooldownUntil.value).getTime() - Date.now()
  if (diff <= 0) return ''
  const totalMins = Math.ceil(diff / 60000)
  const hrs = Math.floor(totalMins / 60)
  const mins = totalMins % 60
  return hrs > 0 ? (mins > 0 ? `${hrs}h ${mins}m` : `${hrs}h`) : `${mins}m`
})

async function logDashMood(emoji: string) {
  if (dashMoodSubmitting.value || dashMoodOnCooldown.value) return
  dashMoodSubmitting.value = true
  dashMoodError.value = null
  dashMoodSuccess.value = null
  try {
    const res = await withCelebration(() =>
      api.post<{ entry: { emoji: string; label: string }; streak: number; today_count: number }>('/api/life/mood', {
        emoji,
        note: dashMoodNote.value.trim() || null,
      })
    )
    dashMoodSuccess.value = `${res.entry.label} logged! (${res.today_count}/4 today)`
    dashMoodNote.value = ''
    setTimeout(() => { dashMoodSuccess.value = null }, 3000)
    // Set cooldown for 6 hours from now
    dashMoodCooldownUntil.value = new Date(Date.now() + 6 * 3600000).toISOString()
    await fetchDashboard()
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      // Extract cooldown time from error detail
      const detail = (e.body as Record<string, string>).detail || ''
      const match = detail.match(/(\d{4}-\d{2}-\d{2}T[\d:.]+(?:[Z+\-][\d:]*)?)/)
      if (match) dashMoodCooldownUntil.value = match[1]
      dashMoodError.value = null  // Timer already shows via dashMoodOnCooldown
    } else {
      dashMoodError.value = 'Failed to log mood'
    }
  } finally {
    dashMoodSubmitting.value = false
  }
}

// Re-fetch dashboard when switching back to overview
watch(activeTab, (tab) => {
  if (tab === 'dashboard') { fetchDashboard(); fetchGamification() }
  // Clear stale errors when switching tabs
  journalError.value = null
  habitError.value = null
  goalError.value = null
  medError.value = null
})

// Listen for logo click → return to dashboard
function handleLogoHome() { navigateTo('dashboard') }
onMounted(() => document.addEventListener('zugalife-go-home', handleLogoHome))
onUnmounted(() => document.removeEventListener('zugalife-go-home', handleLogoHome))

// Listen for settings open from ZugaApp dropdown
function handleOpenSettings() { if (!props.embedded) showSettings.value = true }
onMounted(() => document.addEventListener('zugalife-open-settings', handleOpenSettings))
onUnmounted(() => document.removeEventListener('zugalife-open-settings', handleOpenSettings))

// Module labels for back-nav header
const moduleLabels: Record<Exclude<Tab, 'dashboard'>, string> = {
  journal: 'Journal',
  habits: 'Habits',
  goals: 'Goals',
  meditate: 'Meditate',
  therapist: 'Therapist',
}

// Strip emoji characters from strings (backend embeds emojis in descriptions)
const emojiRe = /[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu
function stripEmoji(s: string): string {
  return s.replace(emojiRe, '').replace(/\s{2,}/g, ' ').trim()
}

// ============================
// MOOD DEFINITIONS (shared by journal compose)
// ============================

const moods = [
  { emoji: '😊', label: 'Happy' },
  { emoji: '😢', label: 'Sad' },
  { emoji: '😠', label: 'Angry' },
  { emoji: '😰', label: 'Anxious' },
  { emoji: '😴', label: 'Tired' },
  { emoji: '🤩', label: 'Excited' },
  { emoji: '😐', label: 'Neutral' },
  { emoji: '🥰', label: 'Loved' },
  { emoji: '😤', label: 'Frustrated' },
  { emoji: '🤔', label: 'Thoughtful' },
  { emoji: '😌', label: 'Calm' },
  { emoji: '💪', label: 'Motivated' },
]

// ============================
// JOURNAL
// ============================

interface JournalReflection {
  id: number
  content: string
  model_used: string
  cost: number
  created_at: string
}

interface JournalEntryBrief {
  id: number
  title: string | null
  content_preview: string
  mood_emoji: string | null
  mood_label: string | null
  reflection_count: number
  created_at: string
}

interface JournalEntryFull {
  id: number
  user_id: string
  title: string | null
  content: string
  mood_emoji: string | null
  mood_label: string | null
  reflections: JournalReflection[]
  created_at: string
  updated_at: string
}

interface JournalListResponse {
  entries: JournalEntryBrief[]
  total: number
}

interface JournalReflectResponse {
  reflection: JournalReflection
  remaining: number
}

type JournalViewState = 'list' | 'compose' | 'detail'
const journalView = ref<JournalViewState>('list')

const journalEntries = ref<JournalEntryBrief[]>([])
const totalJournalEntries = ref(0)
const loadingJournal = ref(true)

const composeTitle = ref('')
const composeContent = ref('')
const composeMood = ref<string | null>(null)
const journalSubmitting = ref(false)

const currentEntry = ref<JournalEntryFull | null>(null)
const loadingDetail = ref(false)
const reflecting = ref(false)
const reflectionsRemaining = ref(3)

const journalError = ref<string | null>(null)
const journalSuccess = ref<string | null>(null)

const contentLength = computed(() => composeContent.value.length)

const composeMoodLabel = computed(() => {
  if (!composeMood.value) return null
  return moods.find(m => m.emoji === composeMood.value)?.label ?? null
})

const groupedJournalEntries = computed(() => {
  const groups: { label: string; entries: JournalEntryBrief[] }[] = []
  const today = new Date().toDateString()
  const yesterday = new Date(Date.now() - 86400000).toDateString()

  for (const entry of journalEntries.value) {
    const dayStr = parseUTC(entry.created_at).toDateString()
    let label: string
    if (dayStr === today) label = 'Today'
    else if (dayStr === yesterday) label = 'Yesterday'
    else label = parseUTC(entry.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

    const last = groups[groups.length - 1]
    if (last && last.label === label) {
      last.entries.push(entry)
    } else {
      groups.push({ label, entries: [entry] })
    }
  }
  return groups
})

function goToCompose() {
  composeTitle.value = ''
  composeContent.value = ''
  composeMood.value = null
  journalError.value = null
  journalView.value = 'compose'
}

function goToJournalList() {
  currentEntry.value = null
  journalError.value = null
  journalView.value = 'list'
}

async function goToDetail(id: number) {
  loadingDetail.value = true
  journalError.value = null
  journalView.value = 'detail'

  try {
    currentEntry.value = await api.get<JournalEntryFull>(`/api/life/journal/${id}`)
    reflectionsRemaining.value = 3 - (currentEntry.value?.reflections.length ?? 0)
  } catch (e) {
    if (e instanceof ApiError) {
      journalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      journalError.value = 'Network error — is the backend running?'
    }
  } finally {
    loadingDetail.value = false
  }
}

async function fetchJournalEntries() {
  try {
    const res = await api.get<JournalListResponse>('/api/life/journal?days=90&limit=50')
    journalEntries.value = res.entries
    totalJournalEntries.value = res.total
  } catch {
    // Silent
  }
}

async function saveEntry() {
  if (!composeContent.value.trim() || journalSubmitting.value) return

  journalSubmitting.value = true
  journalError.value = null

  try {
    const res = await withCelebration(() =>
      api.post<JournalEntryFull>('/api/life/journal', {
        title: composeTitle.value.trim() || null,
        content: composeContent.value.trim(),
        mood_emoji: composeMood.value,
      })
    )
    journalSuccess.value = 'Journal entry saved!'
    setTimeout(() => { journalSuccess.value = null }, 2000)
    await fetchJournalEntries()
    currentEntry.value = res
    reflectionsRemaining.value = 3
    journalView.value = 'detail'
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      journalError.value = body.detail ?? `Error (${e.status})`
    } else {
      journalError.value = 'Network error — is the backend running?'
    }
  } finally {
    journalSubmitting.value = false
  }
}

async function requestReflection() {
  if (!currentEntry.value || reflecting.value) return

  reflecting.value = true
  journalError.value = null

  try {
    const res = await api.post<JournalReflectResponse>(
      `/api/life/journal/${currentEntry.value.id}/reflect`,
    )
    currentEntry.value.reflections.push(res.reflection)
    reflectionsRemaining.value = res.remaining
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      if (e.status === 402) {
        journalError.value = 'AI budget exhausted for today. Try again tomorrow.'
      } else if (e.status === 429) {
        journalError.value = body.detail ?? 'Maximum reflections reached for this entry.'
      } else {
        journalError.value = body.detail ?? `Error (${e.status})`
      }
    } else {
      journalError.value = 'Network error — is the backend running?'
    }
  } finally {
    reflecting.value = false
  }
}

async function deleteEntry() {
  if (!currentEntry.value) return
  journalError.value = null
  try {
    await api.delete(`/api/life/journal/${currentEntry.value.id}`)
    journalSuccess.value = 'Entry deleted.'
    setTimeout(() => { journalSuccess.value = null }, 2000)
    await fetchJournalEntries()
    goToJournalList()
  } catch (e) {
    if (e instanceof ApiError) {
      journalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      journalError.value = 'Network error'
    }
  }
}

// --- Single entry export ---
const showExportMenu = ref(false)

async function exportEntry(format: 'markdown' | 'json') {
  if (!currentEntry.value) return
  showExportMenu.value = false
  try {
    const resp = await fetch(`/api/life/journal/${currentEntry.value.id}/export?format=${format}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new Error(`Export failed (${resp.status})`)
    const blob = await resp.blob()
    const disposition = resp.headers.get('Content-Disposition') ?? ''
    const match = disposition.match(/filename=(.+)/)
    const filename = match ? match[1] : `entry-${currentEntry.value.id}.${format === 'json' ? 'json' : 'md'}`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    journalError.value = 'Export failed'
  }
}

// ============================
// HABIT TRACKING
// ============================

interface HabitDefinition {
  id: number
  name: string
  emoji: string
  unit: string | null
  default_target: number | null
  is_preset: boolean
  is_active: boolean
  sort_order: number
  weekly_target: number | null
  created_at: string
}

interface HabitCheckInItem {
  habit: HabitDefinition
  logged: boolean
  amount: number | null
  log_id: number | null
}

interface DailyCheckInResponse {
  date: string
  habits: HabitCheckInItem[]
  completed_count: number
  total_count: number
}

interface HabitStreakInfo {
  habit_id: number
  habit_name: string
  habit_emoji: string
  current_streak: number
  longest_streak: number
}

interface AllStreaksResponse {
  habits: HabitStreakInfo[]
  overall_current: number
  overall_longest: number
}

interface DayHistory {
  date: string
  completed_count: number
  total_active: number
  completion_rate: number
  habits_done: string[]
}

interface HabitHistoryResponse {
  days: DayHistory[]
  period_days: number
}

interface HabitInsight {
  id: number
  content: string
  model_used: string
  cost: number
  week_start: string
  created_at: string
}

interface HabitInsightListResponse {
  insights: HabitInsight[]
  total: number
}

type HabitView = 'checkin' | 'history' | 'insights' | 'manage'
const habitView = ref<HabitView>('checkin')

const habitCheckin = ref<DailyCheckInResponse | null>(null)
const habitStreaks = ref<AllStreaksResponse | null>(null)
const habitHistory = ref<HabitHistoryResponse | null>(null)
const habitInsights = ref<HabitInsight[]>([])
const allHabits = ref<HabitDefinition[]>([])
const loadingHabits = ref(true)
const habitError = ref<string | null>(null)
const habitSuccess = ref<string | null>(null)
const habitSubmitting = ref(false)
const insightGenerating = ref(false)
const historyDays = ref(7)

// New custom habit form
const newHabitName = ref('')
const newHabitIcon = ref('')  // Stores a Lucide icon name (e.g. 'dumbbell')
const newHabitUnit = ref('')
const newHabitTarget = ref<number | null>(null)
const showNewHabitForm = ref(false)
const showMoreIcons = ref(false)

// Temp amount inputs keyed by habit_id
const amountInputs = ref<Record<number, string>>({})

const completionPercent = computed(() => {
  if (!habitCheckin.value || habitCheckin.value.total_count === 0) return 0
  return Math.round((habitCheckin.value.completed_count / habitCheckin.value.total_count) * 100)
})

async function fetchHabitCheckin() {
  try {
    habitCheckin.value = await api.get<DailyCheckInResponse>('/api/life/habits/checkin')
    // Init amount inputs from existing logs
    if (habitCheckin.value) {
      for (const item of habitCheckin.value.habits) {
        if (item.amount !== null) {
          amountInputs.value[item.habit.id] = String(item.amount)
        }
      }
    }
  } catch { /* silent */ }
}

async function fetchHabitStreaks() {
  try {
    habitStreaks.value = await api.get<AllStreaksResponse>('/api/life/habits/streaks')
  } catch { /* silent */ }
}

async function fetchAllHabits() {
  try {
    allHabits.value = await api.get<HabitDefinition[]>('/api/life/habits')
  } catch { /* silent */ }
}

async function fetchHabitHistory() {
  try {
    habitHistory.value = await api.get<HabitHistoryResponse>(`/api/life/habits/history?days=${historyDays.value}`)
  } catch { /* silent */ }
}

async function fetchHabitInsights() {
  try {
    const res = await api.get<HabitInsightListResponse>('/api/life/habits/insights')
    habitInsights.value = res.insights
  } catch { /* silent */ }
}

async function toggleHabit(item: HabitCheckInItem) {
  habitError.value = null
  try {
    if (item.logged) {
      // Uncheck — use server's date from checkin response (not local date)
      const serverDate = habitCheckin.value?.date
      if (!serverDate) return
      await api.delete(`/api/life/habits/log/${item.habit.id}/${serverDate}`)
      await fetchHabitCheckin()
    } else {
      // Check — celebrate XP gain
      const amt = amountInputs.value[item.habit.id]
      await withCelebration(() =>
        api.post('/api/life/habits/log', {
          habit_id: item.habit.id,
          completed: true,
          amount: amt ? parseFloat(amt) : null,
        })
      )
      await fetchHabitCheckin()
      fetchGamification()
    }
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

async function updateHabitAmount(item: HabitCheckInItem) {
  const amt = amountInputs.value[item.habit.id]
  if (!amt) return
  habitError.value = null
  try {
    await api.post('/api/life/habits/log', {
      habit_id: item.habit.id,
      completed: true,
      amount: parseFloat(amt),
    })
    await fetchHabitCheckin()
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

async function createCustomHabit() {
  if (!newHabitName.value.trim() || !newHabitIcon.value || habitSubmitting.value) return

  habitSubmitting.value = true
  habitError.value = null

  try {
    // Store the icon name as the emoji field (backend treats it as a display string)
    await api.post('/api/life/habits', {
      name: newHabitName.value.trim(),
      emoji: newHabitIcon.value,
      unit: newHabitUnit.value.trim() || null,
      default_target: newHabitTarget.value || null,
    })
    newHabitName.value = ''
    newHabitIcon.value = ''
    newHabitUnit.value = ''
    newHabitTarget.value = null
    showNewHabitForm.value = false
    habitSuccess.value = 'Habit created!'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  } finally {
    habitSubmitting.value = false
  }
}

async function toggleHabitActive(habit: HabitDefinition) {
  habitError.value = null
  try {
    await api.patch(`/api/life/habits/${habit.id}`, { is_active: !habit.is_active })
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

async function deleteCustomHabit(habit: HabitDefinition) {
  habitError.value = null
  try {
    await api.delete(`/api/life/habits/${habit.id}`)
    habitSuccess.value = 'Habit deleted.'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

// --- Habit Resets ---

const resetConfirm = ref<'today' | 'history' | null>(null)
const resettingHabit = ref<number | null>(null)

async function resetToday() {
  habitError.value = null
  try {
    const res = await api.delete<{ deleted: number }>('/api/life/habits/reset/today')
    habitSuccess.value = `Cleared ${res.deleted} check-ins for today.`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    resetConfirm.value = null
    await Promise.all([fetchHabitCheckin(), fetchHabitStreaks()])
  } catch { habitError.value = 'Reset failed.' }
}

async function resetAllHistory() {
  habitError.value = null
  try {
    const res = await api.delete<{ deleted: number }>('/api/life/habits/reset/history')
    habitSuccess.value = `Cleared ${res.deleted} total logs. Fresh start!`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    resetConfirm.value = null
    await Promise.all([fetchHabitCheckin(), fetchHabitStreaks()])
  } catch { habitError.value = 'Reset failed.' }
}

async function resetSingleHabit(habitId: number) {
  habitError.value = null
  try {
    const res = await api.delete<{ deleted: number; habit: string }>(`/api/life/habits/reset/${habitId}`)
    habitSuccess.value = `Reset "${res.habit}" — ${res.deleted} logs cleared.`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    resettingHabit.value = null
    await Promise.all([fetchHabitCheckin(), fetchHabitStreaks()])
  } catch { habitError.value = 'Reset failed.' }
}

async function generateHabitInsight() {
  if (insightGenerating.value) return
  insightGenerating.value = true
  habitError.value = null

  try {
    await api.post('/api/life/habits/insight')
    habitSuccess.value = 'Insight generated!'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await fetchHabitInsights()
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      if (e.status === 402) {
        habitError.value = 'AI budget exhausted for today. Try again tomorrow.'
      } else if (e.status === 429) {
        habitError.value = body.detail ?? 'Insight cooldown active.'
      } else if (e.status === 503) {
        habitError.value = 'AI insights not available in standalone mode.'
      } else {
        habitError.value = body.detail ?? `Error (${e.status})`
      }
    } else {
      habitError.value = 'Network error'
    }
  } finally {
    insightGenerating.value = false
  }
}

const habitUnits = [
  { value: 'minutes', label: '(time)' },
  { value: 'hours', label: '(time)' },
  { value: 'glasses', label: '(volume)' },
  { value: 'steps', label: '(distance)' },
  { value: 'miles', label: '(distance)' },
  { value: 'km', label: '(distance)' },
  { value: 'calories', label: '(energy)' },
  { value: 'servings', label: '(food)' },
  { value: 'pages', label: '(reading)' },
  { value: 'chapters', label: '(reading)' },
  { value: 'reps', label: '(exercise)' },
  { value: 'sets', label: '(exercise)' },
  { value: 'sessions', label: '(count)' },
  { value: 'count', label: '(general)' },
]

// ============================
// GOALS
// ============================

interface GoalMilestone {
  id: number
  goal_id: number
  title: string
  is_completed: boolean
  sort_order: number
  created_at: string
  completed_at: string | null
}

interface LinkedHabit {
  habit_id: number
  habit_name: string
  habit_emoji: string
  days_completed: number
  days_total: number
}

interface Goal {
  id: number
  title: string
  description: string | null
  deadline: string | null
  is_completed: boolean
  sort_order: number
  completed_at: string | null
  created_at: string
  updated_at: string
  template_key: string | null
  milestones: GoalMilestone[]
  milestone_count: number
  milestone_done: number
  linked_habits: LinkedHabit[]
}

interface GoalListResponse {
  active: Goal[]
  completed: Goal[]
}

interface GoalTemplate {
  key: string
  title: string
  description: string
  suggested_habits: string[]
  already_adopted: boolean
}

interface WeeklyTargetItem {
  habit_id: number
  habit_name: string
  habit_emoji: string
  weekly_target: number
  this_week_count: number
  progress_pct: number
}

interface WeeklyTargetsResponse {
  habits: WeeklyTargetItem[]
  week_start: string
}

type GoalSubView = 'goals' | 'weekly'
const goalSubView = ref<GoalSubView>('goals')

const activeGoals = ref<Goal[]>([])
const completedGoals = ref<Goal[]>([])
const weeklyTargets = ref<WeeklyTargetItem[]>([])
const loadingGoals = ref(true)
const goalError = ref<string | null>(null)
const goalSuccess = ref<string | null>(null)

// Create goal form
type GoalCreateMode = 'none' | 'templates' | 'custom'
const goalCreateMode = ref<GoalCreateMode>('none')
const goalTemplates = ref<GoalTemplate[]>([])
const templateAdopting = ref<string | null>(null)
const newGoalTitle = ref('')
const newGoalDescription = ref('')
const newGoalDeadline = ref('')
const goalSubmitting = ref(false)

// Expanded goals (to show milestones)
const expandedGoals = ref<Set<number>>(new Set())

// Add milestone form (per goal)
const addingMilestoneTo = ref<number | null>(null)
const newMilestoneTitle = ref('')

// Habit linking
const linkingHabitTo = ref<number | null>(null)

// Editing goal
const editingGoalId = ref<number | null>(null)
const editGoalTitle = ref('')
const editGoalDescription = ref('')
const editGoalDeadline = ref('')
const editGoalSaving = ref(false)

function startEditGoal(goal: Goal) {
  editingGoalId.value = goal.id
  editGoalTitle.value = goal.title
  editGoalDescription.value = goal.description || ''
  editGoalDeadline.value = goal.deadline || ''
  expandedGoals.value.add(goal.id)
}

function cancelEditGoal() {
  editingGoalId.value = null
  editGoalTitle.value = ''
  editGoalDescription.value = ''
  editGoalDeadline.value = ''
}

async function saveEditGoal(goalId: number) {
  if (!editGoalTitle.value.trim() || editGoalSaving.value) return
  editGoalSaving.value = true
  goalError.value = null
  try {
    await api.patch(`/api/life/goals/${goalId}`, {
      title: editGoalTitle.value.trim(),
      description: editGoalDescription.value.trim() || null,
      deadline: editGoalDeadline.value || null,
    })
    editingGoalId.value = null
    goalSuccess.value = 'Goal updated!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    editGoalSaving.value = false
  }
}

// Editing weekly target
const editingTargetFor = ref<number | null>(null)
const editTargetValue = ref<number | null>(null)

function toggleGoalExpand(id: number) {
  if (expandedGoals.value.has(id)) {
    expandedGoals.value.delete(id)
  } else {
    expandedGoals.value.add(id)
  }
}

async function fetchGoals() {
  try {
    const res = await api.get<GoalListResponse>('/api/life/goals')
    activeGoals.value = res.active
    completedGoals.value = res.completed
  } catch { /* silent */ }
}

async function fetchGoalTemplates() {
  try {
    goalTemplates.value = await api.get<GoalTemplate[]>('/api/life/goals/templates')
  } catch { /* silent */ }
}

async function adoptTemplate(key: string) {
  if (templateAdopting.value) return
  templateAdopting.value = key
  goalError.value = null
  try {
    await api.post('/api/life/goals/from-template', { template_key: key })
    goalSuccess.value = 'Goal created from template!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    goalCreateMode.value = 'none'
    await Promise.all([fetchGoals(), fetchGoalTemplates()])
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    templateAdopting.value = null
  }
}

async function linkHabit(goalId: number, habitId: number) {
  goalError.value = null
  try {
    await api.post(`/api/life/goals/${goalId}/habits`, { habit_id: habitId })
    linkingHabitTo.value = null
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function unlinkHabit(goalId: number, habitId: number) {
  goalError.value = null
  try {
    await api.delete(`/api/life/goals/${goalId}/habits/${habitId}`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

function availableHabitsForGoal(goal: Goal): HabitDefinition[] {
  const linkedIds = new Set(goal.linked_habits.map(h => h.habit_id))
  return allHabits.value.filter(h => h.is_active && !linkedIds.has(h.id))
}

async function fetchWeeklyTargets() {
  try {
    const res = await api.get<WeeklyTargetsResponse>('/api/life/habits/weekly')
    weeklyTargets.value = res.habits
  } catch { /* silent */ }
}

async function createGoal() {
  if (!newGoalTitle.value.trim() || goalSubmitting.value) return
  goalSubmitting.value = true
  goalError.value = null

  try {
    await api.post('/api/life/goals', {
      title: newGoalTitle.value.trim(),
      description: newGoalDescription.value.trim() || null,
      deadline: newGoalDeadline.value || null,
    })
    newGoalTitle.value = ''
    newGoalDescription.value = ''
    newGoalDeadline.value = ''
    goalCreateMode.value = 'none'
    goalSuccess.value = 'Goal created!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    goalSubmitting.value = false
  }
}

async function toggleGoalComplete(goal: Goal) {
  goalError.value = null
  try {
    await api.patch(`/api/life/goals/${goal.id}/complete`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function deleteGoal(goal: Goal) {
  goalError.value = null
  try {
    await api.delete(`/api/life/goals/${goal.id}`)
    goalSuccess.value = 'Goal deleted.'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function addMilestone(goalId: number) {
  if (!newMilestoneTitle.value.trim()) return
  goalError.value = null
  try {
    await api.post(`/api/life/goals/${goalId}/milestones`, {
      title: newMilestoneTitle.value.trim(),
    })
    newMilestoneTitle.value = ''
    addingMilestoneTo.value = null
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function toggleMilestone(goalId: number, milestone: GoalMilestone) {
  goalError.value = null
  try {
    if (!milestone.is_completed) {
      // Completing a milestone — celebrate XP
      await withCelebration(() =>
        api.patch(`/api/life/goals/${goalId}/milestones/${milestone.id}`, {
          is_completed: true,
        })
      )
    } else {
      // Unchecking — no celebration
      await api.patch(`/api/life/goals/${goalId}/milestones/${milestone.id}`, {
        is_completed: false,
      })
    }
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function deleteMilestone(goalId: number, milestoneId: number) {
  goalError.value = null
  try {
    await api.delete(`/api/life/goals/${goalId}/milestones/${milestoneId}`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function setWeeklyTarget(habitId: number) {
  goalError.value = null
  try {
    await api.patch(`/api/life/habits/${habitId}`, {
      weekly_target: editTargetValue.value || null,
    })
    editingTargetFor.value = null
    editTargetValue.value = null
    await fetchWeeklyTargets()
    await fetchAllHabits()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

function startEditTarget(habit: HabitDefinition) {
  editingTargetFor.value = habit.id
  editTargetValue.value = habit.weekly_target ?? null
}

function goalMilestonePct(goal: Goal): number {
  if (goal.milestone_count === 0) return 0
  return Math.round((goal.milestone_done / goal.milestone_count) * 100)
}

function isOverdue(deadline: string | null): boolean {
  if (!deadline) return false
  return new Date(deadline + 'T23:59:59') < new Date()
}

// ============================
// MEDITATION
// ============================

interface MeditationSession {
  id: number
  type: string
  length: string
  duration_seconds: number
  ambience: string
  voice: string
  focus: string | null
  title: string
  transcript: string
  audio_filename: string
  model_used: string
  tts_model: string
  cost: number
  status: string
  error_message: string | null
  mood_before: string | null
  mood_after: string | null
  is_favorite: boolean
  created_at: string
}

interface MeditationBrief {
  id: number
  type: string
  length: string
  duration_seconds: number
  title: string
  is_favorite: boolean
  mood_after: string | null
  created_at: string
}

interface MeditationListResponse {
  sessions: MeditationBrief[]
  total: number
}

interface MeditationRemainingResponse {
  used: number
  limit: number
  remaining: number
}

const meditationTypes = [
  { key: 'breathing', label: 'Breathing', desc: 'Focus on your breath' },
  { key: 'body_scan', label: 'Body Scan', desc: 'Progressive body awareness' },
  { key: 'loving_kindness', label: 'Loving Kindness', desc: 'Compassion for self & others' },
  { key: 'visualization', label: 'Visualization', desc: 'Guided mental imagery' },
  { key: 'gratitude', label: 'Gratitude', desc: 'Appreciate what matters' },
  { key: 'stress_relief', label: 'Stress Relief', desc: 'Release tension mindfully' },
]

const ambienceOptions = [
  { key: 'rain', label: 'Rain' },
  { key: 'ocean', label: 'Ocean' },
  { key: 'forest', label: 'Forest' },
  { key: 'bowls', label: 'Bowls' },
  { key: 'silence', label: 'Silence' },
]

const lengthOptions = [
  { key: 'short', label: 'Short' },
  { key: 'medium', label: 'Medium' },
  { key: 'long', label: 'Long' },
]

type MedView = 'new' | 'player' | 'history'
const medView = ref<MedView>('new')

// Config state
const medType = ref('breathing')
const medLength = ref('medium')
const medAmbience = ref('rain')
const medVoice = ref('serene')
const medFocus = ref('')

// Generation
const medGenerating = ref(false)
const medGenStage = ref<string | null>(null)
const medError = ref<string | null>(null)
const medSuccess = ref<string | null>(null)

// Active session / player
const medSession = ref<MeditationSession | null>(null)
let medAudioEl: HTMLAudioElement | null = null
const medPlaying = ref(false)
const medProgress = ref(0)
const medCurrentTime = ref(0)
const medDurationSec = ref(0)
const medAmbientVolume = ref(0.4)

// History
const medSessions = ref<MeditationBrief[]>([])
const medTotal = ref(0)
const medRemaining = ref<MeditationRemainingResponse | null>(null)
const loadingMeditation = ref(true)
const medShowFavoritesOnly = ref(false)

// Post-session mood
const medMoodAfter = ref<string | null>(null)

const filteredMedSessions = computed(() => {
  if (!medShowFavoritesOnly.value) return medSessions.value
  return medSessions.value.filter(s => s.is_favorite)
})

const transcriptParagraphs = computed(() => {
  if (!medSession.value) return []
  return medSession.value.transcript
    .replace(/\[PAUSE\s*\d+s?\]/g, '')
    .split('\n\n')
    .map(p => p.trim())
    .filter(p => p.length > 0)
})

const activeParagraphIndex = computed(() => {
  if (!transcriptParagraphs.value.length) return 0
  const idx = Math.floor((medProgress.value / 100) * transcriptParagraphs.value.length)
  return Math.min(idx, transcriptParagraphs.value.length - 1)
})

async function fetchMedRemaining() {
  try {
    medRemaining.value = await api.get<MeditationRemainingResponse>('/api/life/meditation/remaining')
  } catch { /* silent */ }
}

async function fetchMedSessions() {
  try {
    const res = await api.get<MeditationListResponse>('/api/life/meditation/sessions')
    medSessions.value = res.sessions
    medTotal.value = res.total
  } catch { /* silent */ }
}

async function generateMeditation() {
  if (medGenerating.value) return
  medGenerating.value = true
  medGenStage.value = null
  medError.value = null

  const payload: Record<string, unknown> = {
    type: medType.value,
    length: medLength.value,
    ambience: medAmbience.value,
    voice: medVoice.value,
  }
  if (medFocus.value.trim()) {
    payload.focus = medFocus.value.trim()
  }

  try {
    // POST returns immediately with a stub session (status="generating")
    const stub = await api.post<MeditationSession>('/api/life/meditation/generate', payload)

    if (stub.status === 'failed') {
      medError.value = stub.error_message ?? 'Generation failed'
      return
    }

    // Poll until ready or failed — no timeout, keeps going
    const sessionId = stub.id
    const startTime = Date.now()
    let polls = 0

    while (true) {
      await new Promise(r => setTimeout(r, 3000))
      polls++

      // Update progress message based on elapsed time
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      if (elapsed < 15) medGenStage.value = 'Writing your meditation script...'
      else if (elapsed < 60) medGenStage.value = 'Expanding into full script...'
      else if (elapsed < 180) medGenStage.value = `Generating voice audio... (${Math.floor(elapsed / 60)}m ${elapsed % 60}s)`
      else medGenStage.value = `Almost done... (${Math.floor(elapsed / 60)}m ${elapsed % 60}s)`

      try {
        const session = await api.get<MeditationSession>(`/api/life/meditation/sessions/${sessionId}`)

        if (session.status === 'ready') {
          medSession.value = session
          medMoodAfter.value = null
          medView.value = 'player'
          medSuccess.value = 'Meditation generated!'
          setTimeout(() => { medSuccess.value = null }, 2000)
          await fetchMedRemaining()
          await fetchMedSessions()
          // Celebrate XP gain from meditation completion
          if (gamificationData.value) {
            celebration.takeSnapshot(gamificationData.value)
            try {
              const newGam = await api.get<GamificationData>('/api/life/gamification')
              celebration.celebrateChanges(newGam, ALL_BADGES.value)
              if (celebration.soundEnabled.value) {
                if (celebration.activeLevelUp.value) playLevelUpSound()
                else if (celebration.activeBadge.value) playBadgeSound()
                else playXpSound()
              }
              gamificationData.value = newGam
            } catch { /* non-critical */ }
          }
          setTimeout(() => loadAndPlayAudio(), 300)
          return
        }

        if (session.status === 'failed') {
          medError.value = session.error_message ?? 'Generation failed'
          return
        }
      } catch {
        // Transient network error — keep polling
        if (polls > 200) {
          // Safety valve: 10 min absolute max
          medError.value = 'Generation is taking unusually long. Check session history later.'
          return
        }
      }
    }
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 402) {
        medError.value = 'AI budget exhausted for today.'
      } else if (e.status === 429) {
        medError.value = detail ?? 'Daily meditation limit reached.'
      } else if (e.status === 503) {
        medError.value = 'Meditation generation not available.'
      } else {
        medError.value = detail ?? `Error (${e.status})`
      }
    } else {
      medError.value = 'Network error'
    }
  } finally {
    medGenerating.value = false
    medGenStage.value = null
  }
}

let medAudioLoading = false

async function loadAndPlayAudio() {
  if (!medSession.value || medAudioLoading) return
  medAudioLoading = true
  medError.value = null
  stopAudio()

  try {
    const token = getToken()
    const res = await fetch(`/api/life/meditation/audio/${medSession.value.audio_filename}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('Audio fetch failed')

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.volume = 0.85
    medAudioEl = audio

    audio.addEventListener('loadedmetadata', () => {
      medDurationSec.value = audio.duration
    })
    audio.addEventListener('timeupdate', () => {
      medCurrentTime.value = audio.currentTime
      if (audio.duration > 0) {
        medProgress.value = (audio.currentTime / audio.duration) * 100
      }
    })
    audio.addEventListener('ended', async () => {
      medPlaying.value = false
      medProgress.value = 100
      stopAmbient()
      // Mark session as completed — awards XP with celebration, then refresh challenges
      if (medSession.value) {
        try {
          await withCelebration(() =>
            api.post(`/api/life/meditation/sessions/${medSession.value!.id}/complete`)
          )
          await fetchGamification()
        } catch { /* non-critical */ }
      }
    })

    // Start voice + ambience together
    if (medSession.value.ambience !== 'silence') {
      startAmbience(medSession.value.ambience as 'rain' | 'ocean' | 'forest' | 'bowls', medAmbientVolume.value)
    }
    await audio.play()
    medPlaying.value = true
  } catch {
    medError.value = 'Failed to load audio'
  } finally {
    medAudioLoading = false
  }
}

function togglePlayPause() {
  if (!medAudioEl) {
    loadAndPlayAudio()
    return
  }
  if (medPlaying.value) {
    medAudioEl.pause()
    pauseAmbience()
    medPlaying.value = false
  } else {
    medAudioEl.play()
    resumeAmbience()
    medPlaying.value = true
  }
}

function seekAudio(event: MouseEvent) {
  if (!medAudioEl || !medDurationSec.value) return
  const bar = event.currentTarget as HTMLElement
  const rect = bar.getBoundingClientRect()
  const pct = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  medAudioEl.currentTime = pct * medDurationSec.value
}

function stopAmbient() {
  stopAmbience()
}

function stopAudio() {
  if (medAudioEl) {
    medAudioEl.pause()
    if (medAudioEl.src.startsWith('blob:')) URL.revokeObjectURL(medAudioEl.src)
    medAudioEl.src = ''
    medAudioEl = null
  }
  stopAmbient()
  medPlaying.value = false
  medProgress.value = 0
  medCurrentTime.value = 0
  medDurationSec.value = 0
}

function updateAmbientVolume(val: number) {
  medAmbientVolume.value = val
  setAmbienceVolume(val)
}

function medFormatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

async function toggleMedFavorite() {
  if (!medSession.value) return
  medError.value = null
  try {
    medSession.value = await api.patch<MeditationSession>(
      `/api/life/meditation/sessions/${medSession.value.id}/favorite`,
    )
    await fetchMedSessions()
  } catch (e) {
    if (e instanceof ApiError) {
      medError.value = (e.body as Record<string, string>).detail ?? 'Error'
    }
  }
}

async function setMedMoodAfter(emoji: string) {
  if (!medSession.value) return
  medMoodAfter.value = emoji
  try {
    medSession.value = await api.patch<MeditationSession>(
      `/api/life/meditation/sessions/${medSession.value.id}/mood`,
      { emoji },
    )
  } catch { /* silent */ }
}

async function openMedSession(sessionId: number) {
  medError.value = null
  try {
    medSession.value = await api.get<MeditationSession>(
      `/api/life/meditation/sessions/${sessionId}`,
    )
    medMoodAfter.value = medSession.value.mood_after
    medView.value = 'player'
  } catch (e) {
    if (e instanceof ApiError) {
      medError.value = (e.body as Record<string, string>).detail ?? 'Error'
    }
  }
}

async function deleteMedSession(sessionId: number) {
  medError.value = null
  try {
    await api.delete(`/api/life/meditation/sessions/${sessionId}`)
    medSuccess.value = 'Session deleted.'
    setTimeout(() => { medSuccess.value = null }, 2000)
    await fetchMedSessions()
  } catch (e) {
    if (e instanceof ApiError) {
      medError.value = (e.body as Record<string, string>).detail ?? 'Error'
    }
  }
}

function goToNewMeditation() {
  stopAudio()
  medSession.value = null
  medError.value = null
  medView.value = 'new'
}

function getMedTypeLabel(type: string): string {
  return meditationTypes.find(t => t.key === type)?.label ?? type
}

function getMedTypeIcon(type: string) {
  return meditationTypeIcons[type] || meditationTypeIcons.breathing
}

// ============================
// SHARED HELPERS
// ============================

/** Ensure ISO timestamps are treated as UTC (backend omits Z suffix) */
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

// ============================
// THERAPIST
// ============================

interface TherapistMessage {
  role: 'user' | 'assistant'
  content: string
}

interface TherapistSessionNote {
  id: number
  themes: string
  patterns: string | null
  follow_up: string | null
  mood_snapshot: string | null
  message_count: number
  cost: number
  provider: string
  created_at: string
  updated_at: string
}

interface TherapistStatus {
  sessions_used: number
  sessions_limit: number
  sessions_remaining: number
  is_first_session: boolean
}

type TherapistView = 'chat' | 'notes' | 'note-detail'
const therapistView = ref<TherapistView>('chat')

const therapistMessages = ref<TherapistMessage[]>([])
const therapistInput = ref('')
const therapistSending = ref(false)
const therapistGreeting = ref('')
const therapistDisclaimer = "I'm an AI companion, not a licensed therapist. I draw from psychology, philosophy, and contemplative traditions to help you reflect. I make mistakes \u2014 please push back when something doesn't feel right."
const therapistStatus = ref<TherapistStatus | null>(null)
const therapistError = ref<string | null>(null)
const therapistSuccess = ref<string | null>(null)
const therapistSessionActive = ref(false)
const therapistEndingSession = ref(false)
const loadingTherapist = ref(true)
const therapistAvailable = ref(true)

const therapistNotes = ref<TherapistSessionNote[]>([])
const therapistCurrentNote = ref<TherapistSessionNote | null>(null)
const therapistEditingNote = ref(false)
const therapistEditThemes = ref('')
const therapistEditPatterns = ref('')
const therapistEditFollowUp = ref('')

const therapistMessagesRemaining = ref(20)

const chatContainer = ref<HTMLElement | null>(null)

watch(therapistMessages, () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}, { deep: true })

async function fetchTherapistStatus() {
  try {
    therapistStatus.value = await api.get<TherapistStatus>('/api/life/therapist/status')
    therapistAvailable.value = true
  } catch {
    therapistAvailable.value = false
  }
}

const GREETING_CACHE_KEY = 'zugalife_therapist_greeting'

function getCachedGreeting(): string | null {
  try {
    const raw = localStorage.getItem(GREETING_CACHE_KEY)
    if (!raw) return null
    const cached = JSON.parse(raw)
    // Expire after 12 hours — stale context is worse than a new AI call
    if (Date.now() - cached.ts > 12 * 60 * 60 * 1000) {
      localStorage.removeItem(GREETING_CACHE_KEY)
      return null
    }
    return cached.greeting
  } catch {
    return null
  }
}

function cacheGreeting(greeting: string) {
  localStorage.setItem(GREETING_CACHE_KEY, JSON.stringify({ greeting, ts: Date.now() }))
}

function clearCachedGreeting() {
  localStorage.removeItem(GREETING_CACHE_KEY)
}

async function fetchTherapistGreeting() {
  try {
    const res = await api.get<{ greeting: string; is_first_session: boolean; disclaimer: string }>('/api/life/therapist/greeting')
    therapistGreeting.value = res.greeting
    cacheGreeting(res.greeting)
  } catch {
    therapistGreeting.value = ''
  }
}

async function fetchTherapistNotes() {
  try {
    const res = await api.get<{ notes: TherapistSessionNote[]; total: number }>('/api/life/therapist/notes')
    therapistNotes.value = res.notes
  } catch { /* silent */ }
}

async function startTherapistSession() {
  therapistMessages.value = []
  therapistSessionActive.value = true
  therapistError.value = null
  therapistMessagesRemaining.value = 20
  therapistSending.value = true

  // Reuse cached greeting if available, otherwise fetch (costs tokens)
  const cached = getCachedGreeting()
  if (cached) {
    therapistGreeting.value = cached
  } else {
    await fetchTherapistGreeting()
  }
  if (therapistGreeting.value) {
    therapistMessages.value.push({ role: 'assistant', content: therapistGreeting.value })
  }
  therapistSending.value = false
}

const therapistRegeneratingGreeting = ref(false)

async function regenerateTherapistGreeting() {
  if (therapistRegeneratingGreeting.value) return
  therapistRegeneratingGreeting.value = true
  try {
    await fetchTherapistGreeting()
    if (therapistGreeting.value && therapistMessages.value.length > 0 && therapistMessages.value[0].role === 'assistant') {
      therapistMessages.value[0].content = therapistGreeting.value
    }
  } finally {
    therapistRegeneratingGreeting.value = false
  }
}

async function sendTherapistMessage() {
  const text = therapistInput.value.trim()
  if (!text || therapistSending.value) return

  therapistInput.value = ''
  therapistMessages.value.push({ role: 'user', content: text })
  therapistSending.value = true
  therapistError.value = null

  try {
    const apiMessages = therapistMessages.value.map(m => ({ role: m.role, content: m.content }))
    const res = await api.post<{ content: string; message_index: number; session_messages_remaining: number; cost: number }>(
      '/api/life/therapist/chat',
      { messages: apiMessages },
    )
    therapistMessages.value.push({ role: 'assistant', content: res.content })
    therapistMessagesRemaining.value = res.session_messages_remaining

    // Auto-end session when limit reached (therapist already wrapped up naturally)
    if (res.session_messages_remaining <= 0) {
      therapistSending.value = false
      await endTherapistSession()
      return
    }
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 429) {
        therapistError.value = detail ?? 'Session limit reached for today.'
      } else if (e.status === 503) {
        therapistError.value = 'Therapist unavailable — Venice may be down.'
        therapistAvailable.value = false
      } else {
        therapistError.value = detail ?? `Error (${e.status})`
      }
    } else {
      therapistError.value = 'Network error — is the backend running?'
    }
  } finally {
    therapistSending.value = false
  }
}

async function endTherapistSession() {
  if (therapistMessages.value.length < 2) {
    therapistSessionActive.value = false
    therapistMessages.value = []
    return
  }

  // Capture messages before clearing UI — user doesn't wait for the save
  const apiMessages = therapistMessages.value.map(m => ({ role: m.role, content: m.content }))
  therapistSessionActive.value = false
  therapistMessages.value = []
  therapistEndingSession.value = false
  clearCachedGreeting()
  therapistView.value = 'chat'

  // Fire celebration toast immediately
  celebration.pushToast({ type: 'info', message: 'Session ended — saving notes...', duration: 3000 })

  // Save in background — no blocking the user
  withCelebration(() =>
    api.post<TherapistSessionNote>('/api/life/therapist/end-session', { messages: apiMessages })
  ).then(async (savedNote) => {
    await fetchTherapistStatus()
    await fetchTherapistNotes()
    therapistCurrentNote.value = savedNote
    celebration.pushToast({ type: 'challenge', message: 'Session notes saved!', duration: 3000 })
  }).catch(() => {
    celebration.pushToast({ type: 'info', message: 'Failed to save session notes', duration: 4000 })
  })
}

async function viewTherapistNote(note: TherapistSessionNote) {
  therapistCurrentNote.value = note
  therapistEditingNote.value = false
  therapistView.value = 'note-detail'
}

function startEditingNote() {
  if (!therapistCurrentNote.value) return
  therapistEditThemes.value = therapistCurrentNote.value.themes
  therapistEditPatterns.value = therapistCurrentNote.value.patterns ?? ''
  therapistEditFollowUp.value = therapistCurrentNote.value.follow_up ?? ''
  therapistEditingNote.value = true
}

async function saveNoteEdit() {
  if (!therapistCurrentNote.value) return
  therapistError.value = null
  try {
    therapistCurrentNote.value = await api.patch<TherapistSessionNote>(
      `/api/life/therapist/notes/${therapistCurrentNote.value.id}`,
      {
        themes: therapistEditThemes.value || undefined,
        patterns: therapistEditPatterns.value || undefined,
        follow_up: therapistEditFollowUp.value || undefined,
      },
    )
    therapistEditingNote.value = false
    therapistSuccess.value = 'Note updated!'
    setTimeout(() => { therapistSuccess.value = null }, 2000)
    await fetchTherapistNotes()
  } catch {
    therapistError.value = 'Failed to update note.'
  }
}

async function deleteTherapistNote(id: number) {
  therapistError.value = null
  try {
    await api.delete(`/api/life/therapist/notes/${id}`)
    therapistNotes.value = therapistNotes.value.filter(n => n.id !== id)
    if (therapistCurrentNote.value?.id === id) {
      therapistCurrentNote.value = null
      therapistView.value = 'notes'
    }
    therapistSuccess.value = 'Note deleted.'
    setTimeout(() => { therapistSuccess.value = null }, 2000)
  } catch {
    therapistError.value = 'Failed to delete note.'
  }
}

// --- Markdown rendering (lightweight — bold, italic, inline code) ---

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')  // escape HTML
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')                     // **bold**
    .replace(/\*(.+?)\*/g, '<em>$1</em>')                                 // *italic*
    .replace(/`(.+?)`/g, '<code class="bg-surface-3 px-1 rounded text-xs">$1</code>')  // `code`
}

// --- Init ---

onMounted(() => {
  // Tier 1 — critical: unblock dashboard as soon as these two resolve
  Promise.all([fetchDashboard(), fetchGamification()])
    .finally(() => { loadingDashboard.value = false })

  // Tier 2 — per-section: each group unblocks its own tab independently
  Promise.all([fetchHabitCheckin(), fetchHabitStreaks(), fetchAllHabits()])
    .finally(() => { loadingHabits.value = false })

  Promise.all([fetchGoals(), fetchGoalTemplates(), fetchWeeklyTargets()])
    .finally(() => { loadingGoals.value = false })

  Promise.all([fetchMedRemaining(), fetchMedSessions()])
    .finally(() => { loadingMeditation.value = false })

  fetchJournalEntries()
    .finally(() => { loadingJournal.value = false })

  Promise.all([fetchTherapistStatus(), fetchTherapistNotes()])
    .finally(() => { loadingTherapist.value = false })

  // Greeting fetched on-demand in startTherapistSession() — don't block page load
})

onUnmounted(() => {
  stopAudio()
})
</script>

<template>
  <div>
    <!-- Animated background layer (fixed position, z-0 renders behind content) -->
    <BackgroundTheme />
    <!-- Celebration overlay (toasts, confetti, modals) -->
    <CelebrationOverlay />

    <div
      class="relative z-10 mx-auto py-10 animate-fade-in"
      :class="activeTab !== 'dashboard'
        ? 'max-w-4xl px-6 mx-4 sm:mx-auto rounded-2xl bg-surface-0/70 backdrop-blur-xl border border-white/[0.04]'
        : 'max-w-7xl px-6'"
    >

    <!-- Success Toasts -->
    <transition name="fade">
      <div
        v-if="journalSuccess || habitSuccess || goalSuccess || medSuccess || therapistSuccess"
        class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-6 py-3 rounded-lg bg-emerald-600 text-white font-medium text-sm shadow-lg"
      >
        {{ journalSuccess || habitSuccess || goalSuccess || medSuccess || therapistSuccess }}
      </div>
    </transition>

    <!-- Back nav + module label (shown on non-dashboard tabs) -->
    <div v-if="activeTab !== 'dashboard'" class="flex items-center gap-3 mb-6">
      <button
        @click="navigateTo('dashboard')"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-txt-muted transition-colors hover:text-txt-primary hover:bg-surface-3/50"
      >
        <ArrowLeft :size="16" />
        <span>Back</span>
      </button>
      <span class="text-sm font-semibold text-txt-primary">{{ moduleLabels[activeTab] }}</span>
      <div class="flex-1" />
      <!-- Persistent XP + Streak bar (visible on every non-dashboard tab) -->
      <div v-if="gamificationData" class="flex items-center gap-3">
        <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <Star :size="12" class="text-amber-400" />
          <span class="text-xs font-bold text-amber-400">Lv.{{ gamificationData.xp.level }}</span>
          <span v-if="gamificationData.xp.prestige_level > 0"
            class="text-[9px] font-bold text-purple-300 bg-purple-500/20 px-1 rounded">P{{ gamificationData.xp.prestige_level }}</span>
        </div>
        <div
          v-if="gamificationData.xp.current_streak_days > 0"
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-orange-500/10 border border-orange-500/20"
        >
          <FlameIcon :size="12" class="text-orange-400" />
          <span class="text-xs font-bold text-orange-300">{{ gamificationData.xp.current_streak_days }}</span>
          <span
            v-if="gamificationData.xp.streak_multiplier > 1"
            class="text-[9px] font-bold text-amber-300 bg-amber-500/20 px-1 rounded"
          >{{ gamificationData.xp.streak_multiplier }}x</span>
        </div>
      </div>
    </div>

    <!-- ===== DASHBOARD TAB ===== -->
    <template v-if="activeTab === 'dashboard'">
      <div v-if="loadingDashboard" class="flex items-center justify-center py-20">
        <div class="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
      </div>

      <template v-else-if="dashboardData">
        <!-- Greeting + settings gear (hidden when embedded in ZugaApp — dashboard already greets) -->
        <div class="flex items-start justify-between mb-8 animate-fade-in">
          <div v-if="!props.embedded" class="inline-block px-5 py-3 rounded-2xl bg-surface-0/60 backdrop-blur-md">
            <p class="text-sm text-txt-muted mb-1">{{ formatDashboardDate(dashboardData.date) }}</p>
            <h2 class="text-2xl font-bold text-txt-primary tracking-tight">{{ dashboardData.greeting }}</h2>
            <p class="text-sm text-txt-secondary mt-1.5">Here's your week at a glance.</p>
          </div>
          <div v-else></div>
          <button
            v-if="!props.embedded"
            @click="showSettings = true"
            class="p-2.5 rounded-xl bg-surface-0/60 backdrop-blur-md border border-bdr text-txt-secondary transition-colors hover:text-txt-primary hover:bg-surface-3/70"
            title="Settings"
          >
            <Settings :size="18" />
          </button>
        </div>

        <!-- XP + Level + Streak Bar -->
        <div v-if="gamificationData" class="glass-card p-4 mb-4 animate-fade-in">
          <div class="flex items-center gap-3">
            <!-- Level badge + prestige stars -->
            <div class="flex-shrink-0 flex flex-col items-center gap-0.5">
              <div class="relative">
                <div class="w-12 h-12 rounded-2xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center"
                  :class="{ 'prestige-glow': gamificationData.xp.prestige_level > 0 }">
                  <span class="text-lg font-bold text-amber-400">{{ gamificationData.xp.level }}</span>
                </div>
                <!-- Prestige stars -->
                <div v-if="gamificationData.xp.prestige_level > 0"
                  class="absolute -top-1.5 -right-1.5 flex items-center gap-px">
                  <span v-for="i in Math.min(gamificationData.xp.prestige_level, 5)" :key="i"
                    class="text-[8px] prestige-star">&#11088;</span>
                  <span v-if="gamificationData.xp.prestige_level > 5"
                    class="text-[7px] font-bold text-amber-300">+{{ gamificationData.xp.prestige_level - 5 }}</span>
                </div>
              </div>
              <span class="text-[10px] text-txt-muted leading-none">{{ gamificationData.xp.level_name }}</span>
            </div>

            <!-- XP progress -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between mb-1">
                <div class="flex items-center gap-1.5">
                  <Zap :size="12" class="text-amber-400" />
                  <span class="text-xs font-semibold text-txt-primary">{{ gamificationData.xp.xp_progress_in_level.toLocaleString() }} / {{ gamificationData.xp.xp_for_next_level.toLocaleString() }} XP</span>
                </div>
                <div class="flex items-center gap-1.5">
                  <span v-if="gamificationData.xp.prestige_multiplier > 1"
                    class="text-[9px] font-bold text-purple-300 bg-purple-500/20 px-1 rounded multiplier-pulse">
                    P{{ gamificationData.xp.prestige_level }} +{{ Math.round((gamificationData.xp.prestige_multiplier - 1) * 100) }}%
                  </span>
                  <span class="text-[10px] text-txt-muted">{{ gamificationData.xp.total_xp.toLocaleString() }} total</span>
                </div>
              </div>
              <div class="w-full bg-surface-3 rounded-full h-2 overflow-hidden">
                <div
                  class="h-2 rounded-full transition-all duration-700 ease-out"
                  :class="gamificationData.xp.can_prestige
                    ? 'bg-gradient-to-r from-purple-500 via-amber-400 to-purple-500 prestige-bar-shimmer'
                    : 'bg-gradient-to-r from-amber-500 to-yellow-400'"
                  :style="{ width: Math.min(100, Math.round((gamificationData.xp.xp_progress_in_level / gamificationData.xp.xp_for_next_level) * 100)) + '%' }"
                ></div>
              </div>
            </div>

            <!-- Streak flame -->
            <div class="flex-shrink-0 flex flex-col items-center gap-0.5">
              <div class="flex items-center gap-1">
                <FlameIcon :size="16" class="text-amber-400" />
                <span class="text-sm font-bold text-txt-primary">{{ gamificationData.xp.current_streak_days }}</span>
              </div>
              <div
                v-if="gamificationData.xp.streak_multiplier > 1"
                class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 leading-none multiplier-pulse"
              >
                {{ gamificationData.xp.streak_multiplier }}x
              </div>
              <span v-else class="text-[10px] text-txt-muted leading-none">streak</span>
            </div>
          </div>

          <!-- Prestige Available Banner -->
          <div v-if="gamificationData.xp.can_prestige"
            class="mt-3 pt-3 border-t border-bdr/50">
            <div class="flex items-center gap-3 p-3 rounded-xl bg-gradient-to-r from-purple-500/10 via-amber-500/10 to-purple-500/10 border border-purple-500/20 prestige-banner-glow">
              <div class="flex-1">
                <p class="text-sm font-bold text-purple-300">Prestige Available!</p>
                <p class="text-[10px] text-txt-muted mt-0.5">Reset to Lv.1 for a permanent +5% XP bonus and a unique badge</p>
              </div>
              <button
                @click="doPrestige"
                :disabled="prestigeLoading"
                class="px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-purple-600 to-amber-500 hover:from-purple-500 hover:to-amber-400 transition-all active:scale-95 disabled:opacity-50 min-h-[36px]"
              >
                {{ prestigeLoading ? 'Ascending...' : 'Prestige' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Mood + Challenges row (side-by-side on desktop) -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">

        <!-- Mood Check-in -->
        <div class="glass-card p-4 animate-fade-in">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-sm font-semibold text-txt-primary">How are you feeling?</span>
            <span v-if="dashboardData?.mood.has_data" class="text-xs text-txt-muted ml-auto">{{ dashboardData.mood.total }} total logs</span>
          </div>

          <!-- Mood grid -->
          <div class="grid grid-cols-6 gap-2 mb-3" :class="dashMoodOnCooldown ? 'opacity-40 pointer-events-none' : ''">
            <button
              v-for="m in moods"
              :key="m.emoji"
              @click="logDashMood(m.emoji)"
              :disabled="dashMoodSubmitting"
              class="flex flex-col items-center gap-1 py-2 rounded-xl hover:bg-surface-3 transition-all active:scale-95"
              :title="m.label"
            >
              <component :is="moodIcons[m.emoji]" :size="22" class="text-amber-400" v-if="moodIcons[m.emoji]" />
              <Meh v-else :size="22" class="text-amber-400" />
              <span class="text-[10px] text-txt-muted">{{ m.label }}</span>
            </button>
          </div>

          <!-- Cooldown notice -->
          <div v-if="dashMoodOnCooldown" class="text-center">
            <p class="text-xs text-txt-muted">Next check-in available in <span class="text-accent">{{ dashMoodTimeLeft }}</span></p>
          </div>

          <!-- Success / Error -->
          <p v-if="dashMoodSuccess" class="text-xs text-emerald-400 text-center">{{ dashMoodSuccess }}</p>
          <p v-if="dashMoodError" class="text-xs text-red-400 text-center">{{ dashMoodError }}</p>

          <!-- Recent moods sparkline -->
          <div v-if="dashboardData?.mood.has_data && dashboardData.mood.recent.length > 0" class="flex items-center gap-1.5 mt-3 pt-3 border-t border-bdr/50">
            <template v-for="(entry, i) in dashboardData.mood.recent.slice(0, 5)" :key="i">
              <div
                class="w-7 h-7 rounded-lg bg-surface-3 flex items-center justify-center transition-transform hover:scale-110"
                :title="entry.label + ' — ' + timeAgo(entry.date)"
              >
                <component :is="moodIcons[entry.emoji]" :size="14" class="text-amber-400" v-if="moodIcons[entry.emoji]" />
                <Meh v-else :size="14" class="text-amber-400" />
              </div>
            </template>
            <span class="text-[10px] text-txt-muted ml-1">recent</span>
          </div>
        </div>

        <!-- Daily Challenges + Weekly Quests (right column on desktop) -->
        <div class="flex flex-col gap-4">

        <!-- Daily Challenges -->
        <div v-if="gamificationData && gamificationData.daily_challenges.length > 0" class="glass-card p-4 animate-fade-in">
          <div class="flex items-center gap-2 mb-3">
            <Target :size="14" class="text-accent" />
            <span class="text-sm font-semibold text-txt-primary">Today's Challenges</span>
            <span class="ml-auto text-xs text-txt-muted">
              {{ gamificationData.daily_challenges.filter(c => c.is_completed).length }}/{{ gamificationData.daily_challenges.length }} done
            </span>
          </div>
          <div class="space-y-2">
            <div
              v-for="challenge in gamificationData.daily_challenges"
              :key="challenge.challenge_key"
              class="flex items-center gap-3 py-2 px-3 rounded-xl transition-colors"
              :class="challenge.is_completed ? 'bg-emerald-500/8' : 'bg-surface-3/60'"
            >
              <CheckCircle2
                v-if="challenge.is_completed"
                :size="16"
                class="flex-shrink-0 text-emerald-400"
              />
              <div
                v-else
                class="flex-shrink-0 w-4 h-4 rounded-full border border-bdr"
              ></div>
              <div class="flex-1 min-w-0">
                <p
                  class="text-xs font-medium leading-tight"
                  :class="challenge.is_completed ? 'text-txt-muted line-through' : 'text-txt-primary'"
                >{{ challenge.title }}</p>
                <p class="text-[10px] text-txt-muted leading-tight mt-0.5">{{ challenge.description }}</p>
              </div>
              <span
                class="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded leading-none"
                :class="challenge.is_completed ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'"
              >+{{ challenge.xp_reward }} XP</span>
            </div>
          </div>
        </div>

        <!-- Weekly Quests -->
        <div v-if="gamificationData && gamificationData.weekly_quests && gamificationData.weekly_quests.length > 0" class="glass-card p-4 animate-fade-in">
          <div class="flex items-center gap-2 mb-3">
            <Star :size="14" class="text-purple-400" />
            <span class="text-sm font-semibold text-txt-primary">Weekly Quests</span>
            <span class="ml-auto text-xs text-txt-muted">
              {{ gamificationData.weekly_quests.filter(q => q.is_completed).length }}/{{ gamificationData.weekly_quests.length }} done
            </span>
          </div>
          <div class="space-y-2">
            <div
              v-for="quest in gamificationData.weekly_quests"
              :key="quest.quest_key"
              class="flex items-center gap-3 py-2.5 px-3 rounded-xl transition-colors"
              :class="quest.is_completed ? 'bg-purple-500/8' : 'bg-surface-3/60 border border-purple-500/10'"
            >
              <CheckCircle2
                v-if="quest.is_completed"
                :size="16"
                class="flex-shrink-0 text-purple-400"
              />
              <div
                v-else
                class="flex-shrink-0 w-4 h-4 rounded-full border-2 border-purple-400/40"
              ></div>
              <div class="flex-1 min-w-0">
                <p
                  class="text-xs font-semibold leading-tight"
                  :class="quest.is_completed ? 'text-txt-muted line-through' : 'text-txt-primary'"
                >{{ quest.title }}</p>
                <p class="text-[10px] text-txt-muted leading-tight mt-0.5">{{ quest.description }}</p>
              </div>
              <span
                class="flex-shrink-0 text-[10px] font-bold px-2 py-0.5 rounded leading-none"
                :class="quest.is_completed ? 'bg-purple-500/15 text-purple-400' : 'bg-purple-500/15 text-purple-300'"
              >+{{ quest.xp_reward }} XP</span>
            </div>
          </div>
        </div>

        </div><!-- /right column (challenges + quests) -->
        </div><!-- /mood+challenges grid -->

        <!-- Badges + XP Activity row -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">

        <!-- Badge Showcase (takes 2 cols on desktop) -->
        <div v-if="gamificationData" class="glass-card p-4 animate-fade-in lg:col-span-2">
          <div class="flex items-center gap-2 mb-3">
            <Trophy :size="14" class="text-accent" />
            <span class="text-sm font-semibold text-txt-primary">Badges</span>
            <span class="ml-auto text-xs text-txt-muted">
              {{ gamificationData.badges.filter(b => b.earned_at !== null).length }}/{{ ALL_BADGES.length }}
            </span>
          </div>
          <div class="flex gap-2 overflow-x-auto pb-2 badge-scroll">
            <div
              v-for="badge in ALL_BADGES"
              :key="badge.key"
              class="flex-shrink-0 flex flex-col items-center gap-1 w-16 p-2 rounded-xl border transition-colors"
              :class="gamificationData.badges.find(b => b.badge_key === badge.key && b.earned_at)
                ? 'bg-amber-500/8 border-amber-500/20'
                : 'bg-surface-3/40 border-bdr/40 opacity-50'"
              :title="badge.description"
            >
              <component
                v-if="gamificationData.badges.find(b => b.badge_key === badge.key && b.earned_at) && (badgeIcons[badge.key] || (badge.key.startsWith('prestige_') && prestigeIcons[(parseInt(badge.key.split('_')[1]) - 1) % prestigeIcons.length]))"
                :is="badgeIcons[badge.key] || prestigeIcons[(parseInt(badge.key.split('_')[1]) - 1) % prestigeIcons.length]"
                :size="22"
                :class="badge.key.startsWith('prestige_') ? 'text-purple-400' : 'text-amber-400'"
              />
              <Lock v-else :size="18" class="text-txt-muted" />
              <span class="text-[9px] text-txt-muted text-center leading-tight line-clamp-2">{{ badge.title }}</span>
            </div>
          </div>
        </div>

        <!-- XP Activity Feed -->
        <div v-if="gamificationData && gamificationData.recent_xp.length > 0" class="glass-card p-4 animate-fade-in">
          <div class="flex items-center gap-2 mb-3">
            <Star :size="14" class="text-accent" />
            <span class="text-sm font-semibold text-txt-primary">Recent XP</span>
          </div>
          <div class="space-y-1.5">
            <div
              v-for="(entry, i) in gamificationData.recent_xp.slice(0, 5)"
              :key="i"
              class="flex items-center gap-2"
            >
              <component
                v-if="xpSourceIcons[entry.source]"
                :is="xpSourceIcons[entry.source]"
                :size="12"
                class="flex-shrink-0 text-txt-muted"
              />
              <span class="text-xs font-semibold text-amber-400 w-14 flex-shrink-0">+{{ entry.amount }} XP</span>
              <span class="text-xs text-txt-muted truncate">{{ stripEmoji(entry.description) }}</span>
            </div>
          </div>
        </div>

        </div><!-- /badges+xp grid -->

        <!-- Analytics Dashboard (main visualization) -->
        <div class="mb-4">
          <AnalyticsDashboard />
        </div>

        <!-- Module Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">

          <!-- HABITS CARD -->
          <button
            @click="navigateTo('habits')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
            style="animation-delay: 50ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <TrendingUp :size="18" class="text-emerald-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Habits</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.habits.has_data">
              <!-- Progress bar -->
              <div class="mb-3">
                <div class="flex items-baseline justify-between mb-1.5">
                  <span class="text-2xl font-bold text-txt-primary">{{ Math.round(dashboardData.habits.completion_rate * 100) }}<span class="text-sm font-normal text-txt-muted">%</span></span>
                  <span class="text-xs text-txt-muted">{{ dashboardData.habits.completed }}/{{ dashboardData.habits.total_possible }}</span>
                </div>
                <div class="w-full bg-surface-3 rounded-full h-2">
                  <div
                    class="h-2 rounded-full transition-all duration-700 ease-out"
                    :class="dashboardData.habits.completion_rate >= 0.8 ? 'bg-emerald-500' : dashboardData.habits.completion_rate >= 0.5 ? 'bg-amber-500' : 'bg-surface-4'"
                    :style="{ width: Math.round(dashboardData.habits.completion_rate * 100) + '%' }"
                  ></div>
                </div>
              </div>
              <!-- Top habits preview -->
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="h in dashboardData.habits.top_habits.slice(0, 3)"
                  :key="h.name"
                  class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-secondary"
                >
                  <component :is="getIcon(h.emoji)" :size="11" v-if="getIcon(h.emoji)" />
                  {{ h.name }}
                  <span class="text-txt-muted">{{ h.completed }}/{{ h.total }}</span>
                </span>
              </div>
            </template>
            <template v-else>
              <p class="text-sm text-txt-muted">Build consistent routines</p>
              <p class="text-xs text-txt-muted mt-1">Set up your first habits</p>
            </template>
          </button>

          <!-- GOALS CARD -->
          <button
            @click="navigateTo('goals')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
            style="animation-delay: 100ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-sky-500/10 flex items-center justify-center">
                  <Target :size="18" class="text-sky-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Goals</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.goals.has_data">
              <div class="flex-1 flex flex-col">
                <div class="flex items-baseline gap-4 mb-3">
                  <div>
                    <span class="text-2xl font-bold text-txt-primary">{{ dashboardData.goals.active }}</span>
                    <span class="text-xs text-txt-muted ml-1">active</span>
                  </div>
                  <div v-if="dashboardData.goals.completed > 0">
                    <span class="text-lg font-semibold text-emerald-400">{{ dashboardData.goals.completed }}</span>
                    <span class="text-xs text-txt-muted ml-1">done</span>
                  </div>
                </div>
                <div v-if="dashboardData.goals.milestones_total > 0" class="mb-2">
                  <div class="flex items-center justify-between text-xs text-txt-muted mb-1">
                    <span>Milestones</span>
                    <span>{{ dashboardData.goals.milestones_done }}/{{ dashboardData.goals.milestones_total }}</span>
                  </div>
                  <div class="w-full bg-surface-3 rounded-full h-2">
                    <div
                      class="h-2 rounded-full bg-sky-500 transition-all duration-500"
                      :style="{ width: Math.round((dashboardData.goals.milestones_done / dashboardData.goals.milestones_total) * 100) + '%' }"
                    ></div>
                  </div>
                </div>
                <div v-if="dashboardData.goals.nearest_deadline" class="flex items-center gap-1.5 text-xs text-txt-muted mt-auto">
                  <CalendarDays :size="12" />
                  <span>{{ dashboardData.goals.nearest_deadline.title }}</span>
                  <span class="text-txt-muted">·</span>
                  <span>{{ formatDeadline(dashboardData.goals.nearest_deadline.date) }}</span>
                </div>
              </div>
            </template>
            <template v-else>
              <div class="flex-1 flex flex-col justify-center">
                <p class="text-sm text-txt-muted mb-2">Set meaningful goals</p>
                <p class="text-xs text-txt-muted mb-3">Choose from templates or create your own</p>
                <div class="flex flex-wrap gap-1.5">
                  <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Fitness</span>
                  <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Learning</span>
                  <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Career</span>
                </div>
              </div>
            </template>
          </button>

          <!-- MEDITATION CARD -->
          <button
            @click="navigateTo('meditate')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group"
            style="animation-delay: 150ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center">
                  <BrainIcon :size="18" class="text-violet-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Meditation</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.meditation.has_data && dashboardData.meditation.sessions_this_week > 0">
              <div class="flex items-baseline gap-4 mb-2">
                <div>
                  <span class="text-2xl font-bold text-txt-primary">{{ dashboardData.meditation.sessions_this_week }}</span>
                  <span class="text-xs text-txt-muted ml-1">this week</span>
                </div>
                <div>
                  <span class="text-lg font-semibold text-txt-secondary">{{ dashboardData.meditation.total_minutes }}</span>
                  <span class="text-xs text-txt-muted ml-1">min</span>
                </div>
              </div>
              <p class="text-xs text-txt-muted">{{ dashboardData.meditation.total_sessions }} total sessions · avg {{ dashboardData.meditation.avg_minutes }} min</p>
            </template>
            <template v-else-if="dashboardData.meditation.has_data">
              <p class="text-sm text-txt-secondary">No sessions this week</p>
              <p class="text-xs text-txt-muted mt-1">{{ dashboardData.meditation.total_sessions }} total sessions</p>
            </template>
            <template v-else>
              <p class="text-sm text-txt-muted">AI-guided meditation</p>
              <p class="text-xs text-txt-muted mt-1">Breathing, body scan, gratitude & more</p>
            </template>
          </button>

          <!-- JOURNAL & MOOD CARD -->
          <button
            @click="navigateTo('journal')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group"
            style="animation-delay: 200ms"
          >
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-rose-500/10 flex items-center justify-center">
                  <BookOpen :size="18" class="text-rose-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Journal & Mood</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.journal.has_data">
              <div class="flex items-baseline gap-1 mb-1">
                <span class="text-2xl font-bold text-txt-primary">{{ dashboardData.journal.entries_this_week }}</span>
                <span class="text-xs text-txt-muted">entries this week</span>
              </div>
              <p v-if="dashboardData.journal.latest_title" class="text-xs text-txt-muted truncate mb-2">
                Latest: {{ dashboardData.journal.latest_title }}
              </p>
              <p class="text-xs text-txt-muted">{{ dashboardData.journal.total }} total entries</p>
            </template>
            <template v-else>
              <p class="text-sm text-txt-muted">Write, reflect, understand</p>
              <p class="text-xs text-txt-muted mt-1">Start your first journal entry</p>
            </template>
            <!-- Mood sparkline -->
            <div v-if="dashboardData.mood.has_data && dashboardData.mood.recent.length > 0" class="flex items-center gap-1.5 mt-3 pt-3 border-t border-bdr">
              <template v-for="(entry, i) in dashboardData.mood.recent.slice(0, 5)" :key="i">
                <div
                  class="w-7 h-7 rounded-lg bg-surface-3 flex items-center justify-center transition-transform hover:scale-110"
                  :title="entry.label + ' — ' + timeAgo(entry.date)"
                >
                  <component :is="moodIcons[entry.emoji]" :size="14" class="text-amber-400" v-if="moodIcons[entry.emoji]" />
                  <Meh v-else :size="14" class="text-amber-400" />
                </div>
              </template>
              <span class="text-xs text-txt-muted ml-1">recent moods</span>
            </div>
          </button>

          <!-- THERAPIST CARD -->
          <button
            @click="navigateTo('therapist')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
            style="animation-delay: 250ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-teal-500/10 flex items-center justify-center">
                  <MessageCircleHeart :size="18" class="text-teal-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Therapist</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.therapist.has_data">
              <p class="text-sm text-txt-secondary mb-2 line-clamp-1">{{ dashboardData.therapist.last_themes }}</p>
              <div class="flex items-center gap-2 text-xs text-txt-muted mt-auto">
                <span v-if="dashboardData.therapist.last_mood" class="px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400">{{ dashboardData.therapist.last_mood }}</span>
                <span>{{ dashboardData.therapist.total_sessions }} sessions</span>
                <span v-if="dashboardData.therapist.last_date">· {{ timeAgo(dashboardData.therapist.last_date) }}</span>
              </div>
            </template>
            <template v-else>
              <p class="text-sm text-txt-muted">AI companion for reflection</p>
              <p class="text-xs text-txt-muted mt-1">Talk through what's on your mind</p>
            </template>
          </button>

        </div>

      </template>
    </template>

    <!-- ===== HABITS TAB ===== -->
    <template v-if="activeTab === 'habits'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'checkin', label: 'Check-in' },
            { key: 'history', label: 'History' },
            { key: 'insights', label: 'Insights' },
            { key: 'manage', label: 'Manage' },
          ] as { key: HabitView; label: string }[]"
          :key="view.key"
          @click="habitView = view.key; if (view.key === 'history') fetchHabitHistory(); if (view.key === 'insights') fetchHabitInsights()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
          :class="habitView === view.key ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
        >
          {{ view.label }}
        </button>
      </div>

      <p v-if="habitError" class="text-sm text-red-400 mb-4">{{ habitError }}</p>

      <!-- ===== CHECK-IN VIEW ===== -->
      <template v-if="habitView === 'checkin'">
        <div v-if="loadingHabits" class="text-sm text-txt-muted">Loading habits...</div>
        <template v-else-if="habitCheckin">
          <!-- Progress bar -->
          <div class="glass-card p-4 mb-6">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-txt-primary">
                {{ habitCheckin.completed_count }}/{{ habitCheckin.total_count }} habits completed
              </span>
              <span class="text-xs text-txt-muted">{{ completionPercent }}%</span>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-2.5">
              <div
                class="h-2.5 rounded-full transition-all duration-500"
                :class="completionPercent === 100 ? 'bg-emerald-500' : 'bg-accent'"
                :style="{ width: completionPercent + '%' }"
              />
            </div>
          </div>

          <!-- Habit cards -->
          <div class="space-y-2">
            <div
              v-for="item in habitCheckin.habits"
              :key="item.habit.id"
              class="glass-card px-4 py-3 flex items-center gap-3 transition-all duration-200"
              :class="item.logged ? 'ring-1 ring-emerald-500/30' : ''"
            >
              <button
                @click="toggleHabit(item)"
                class="w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all flex-shrink-0"
                :class="item.logged
                  ? 'bg-emerald-500 border-emerald-500 text-white'
                  : 'border-bdr hover:border-accent'"
              >
                <span v-if="item.logged" class="text-xs">&#10003;</span>
              </button>
              <component :is="getIcon(item.habit.emoji)" :size="22" class="flex-shrink-0 text-accent" v-if="getIcon(item.habit.emoji)" />
              <CircleDot v-else :size="22" class="flex-shrink-0 text-accent" />
              <div class="flex-1 min-w-0">
                <span class="text-sm font-medium text-txt-primary">{{ item.habit.name }}</span>
              </div>
              <div v-if="item.habit.unit" class="flex items-center gap-1.5">
                <input
                  type="number"
                  :value="amountInputs[item.habit.id] ?? ''"
                  @input="amountInputs[item.habit.id] = ($event.target as HTMLInputElement).value"
                  @blur="updateHabitAmount(item)"
                  @keyup.enter="updateHabitAmount(item)"
                  :placeholder="item.habit.default_target ? String(item.habit.default_target) : '0'"
                  class="w-14 px-1.5 py-1 text-sm text-center rounded-md bg-surface-3 text-txt-primary border border-bdr focus:border-accent focus:outline-none"
                />
                <span class="text-xs text-txt-muted w-12">{{ item.habit.unit }}</span>
              </div>
            </div>
          </div>

          <!-- Reset options -->
          <div class="mt-6 flex flex-wrap gap-2">
            <button
              v-if="resetConfirm !== 'today'"
              @click="resetConfirm = 'today'"
              class="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
            >
              Reset today
            </button>
            <div v-else class="flex items-center gap-2 text-xs animate-fade-in">
              <span class="text-txt-muted">Uncheck all today?</span>
              <button @click="resetToday" class="text-red-400 hover:text-red-300 font-medium">Yes, clear</button>
              <button @click="resetConfirm = null" class="text-txt-muted hover:text-txt-primary">Cancel</button>
            </div>

            <span class="text-txt-muted/30">·</span>

            <button
              v-if="resetConfirm !== 'history'"
              @click="resetConfirm = 'history'"
              class="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
            >
              Reset all history
            </button>
            <div v-else class="flex items-center gap-2 text-xs animate-fade-in">
              <span class="text-red-400">Delete ALL logs &amp; streaks?</span>
              <button @click="resetAllHistory" class="text-red-400 hover:text-red-300 font-medium">Yes, reset everything</button>
              <button @click="resetConfirm = null" class="text-txt-muted hover:text-txt-primary">Cancel</button>
            </div>
          </div>
        </template>
        <div v-else class="glass-card p-8 text-center">
          <p class="text-txt-muted">No habits set up yet.</p>
        </div>
      </template>

      <!-- ===== HISTORY VIEW ===== -->
      <template v-if="habitView === 'history'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">History</h2>
          <div class="flex gap-1">
            <button
              v-for="d in [7, 30]"
              :key="d"
              @click="historyDays = d; fetchHabitHistory()"
              class="px-3 py-1 text-xs rounded-lg transition-colors"
              :class="historyDays === d ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary'"
            >
              {{ d }}d
            </button>
          </div>
        </div>
        <div v-if="!habitHistory" class="text-sm text-txt-muted">Loading...</div>
        <div v-else-if="habitHistory.days.filter(d => d.completed_count > 0).length === 0" class="glass-card p-6 text-center">
          <p class="text-txt-muted">No habit data yet. Start checking in!</p>
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="day in habitHistory.days.filter(d => d.completed_count > 0)"
            :key="day.date"
            class="glass-card px-4 py-3"
          >
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-sm font-medium text-txt-primary">{{ new Date(day.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) }}</span>
              <span class="text-xs text-txt-muted">{{ day.completed_count }}/{{ day.total_active }}</span>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-1.5 mb-1.5">
              <div
                class="h-1.5 rounded-full transition-all"
                :class="day.completion_rate >= 1 ? 'bg-emerald-500' : day.completion_rate > 0 ? 'bg-accent' : 'bg-surface-3'"
                :style="{ width: Math.round(day.completion_rate * 100) + '%' }"
              />
            </div>
            <div v-if="day.habits_done.length > 0" class="flex gap-1 flex-wrap">
              <template v-for="(emoji, i) in day.habits_done" :key="i">
                <component :is="getIcon(emoji)" :size="14" class="text-accent" v-if="getIcon(emoji)" />
                <CircleDot v-else :size="14" class="text-accent" />
              </template>
            </div>
          </div>
        </div>
      </template>

      <!-- ===== INSIGHTS VIEW ===== -->
      <template v-if="habitView === 'insights'">
        <div class="mb-6">
          <button
            @click="generateHabitInsight"
            :disabled="insightGenerating"
            class="btn-primary w-full"
          >
            <span v-if="insightGenerating" class="inline-flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Analyzing patterns...
            </span>
            <span v-else>Get Weekly Insight</span>
          </button>
          <p class="text-xs text-txt-muted text-center mt-2">Correlates your habits with mood data (7-day cooldown)</p>
        </div>
        <div v-if="habitInsights.length === 0" class="glass-card p-6 text-center">
          <p class="text-txt-muted text-sm">No insights yet. Generate your first weekly analysis!</p>
        </div>
        <div v-else class="space-y-3">
          <div v-for="insight in habitInsights" :key="insight.id" class="glass-card p-4 animate-slide-up">
            <div class="flex items-center gap-2 mb-2">
              <span class="text-xs font-medium text-accent">Week of {{ new Date(insight.week_start + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}</span>
              <span class="text-xs text-txt-muted">{{ formatDate(insight.created_at) }}</span>
              <span class="text-xs text-txt-muted ml-auto">${{ insight.cost.toFixed(4) }}</span>
            </div>
            <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ insight.content }}</p>
          </div>
        </div>
      </template>

      <!-- ===== MANAGE VIEW ===== -->
      <template v-if="habitView === 'manage'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">Manage Habits</h2>
          <button
            @click="showNewHabitForm = !showNewHabitForm"
            class="text-sm text-accent hover:text-accent/80 transition-colors"
          >
            {{ showNewHabitForm ? 'Cancel' : '+ Add Custom' }}
          </button>
        </div>

        <!-- New habit form -->
        <div v-if="showNewHabitForm" class="glass-card p-4 mb-4 space-y-3 animate-fade-in">
          <input
            v-model="newHabitName"
            type="text"
            placeholder="Habit name"
            maxlength="50"
            class="input-field"
          />
          <!-- Icon picker grid -->
          <div>
            <p class="text-xs text-txt-muted mb-1.5">Choose an icon:</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="opt in habitIconPicker"
                :key="opt.name"
                @click="newHabitIcon = opt.name"
                class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
                :class="newHabitIcon === opt.name ? 'bg-accent/15 ring-1 ring-accent/50 text-accent' : 'bg-surface-3 text-txt-muted hover:text-txt-primary'"
                :title="opt.label"
              >
                <component :is="opt.icon" :size="18" />
              </button>
            </div>
            <!-- Expand arrow -->
            <button
              @click="showMoreIcons = !showMoreIcons"
              class="mt-2 flex items-center gap-1 text-xs text-txt-muted hover:text-accent transition-colors"
            >
              <component :is="showMoreIcons ? ChevronUp : ChevronDown" :size="14" />
              {{ showMoreIcons ? 'Fewer icons' : 'More icons' }}
            </button>
            <!-- Expanded categories -->
            <div v-if="showMoreIcons" class="mt-2 space-y-2.5 max-h-60 overflow-y-auto pr-1">
              <div v-for="cat in habitIconCategories" :key="cat.label">
                <p class="text-[11px] text-txt-muted uppercase tracking-wider mb-1">{{ cat.label }}</p>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="opt in cat.icons"
                    :key="opt.name"
                    @click="newHabitIcon = opt.name"
                    class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
                    :class="newHabitIcon === opt.name ? 'bg-accent/15 ring-1 ring-accent/50 text-accent' : 'bg-surface-3 text-txt-muted hover:text-txt-primary'"
                    :title="opt.label"
                  >
                    <component :is="opt.icon" :size="18" />
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <div class="flex-1 relative">
              <input
                v-model="newHabitUnit"
                type="text"
                list="habit-unit-suggestions"
                placeholder="No unit (checkbox only)"
                class="input-field w-full text-sm"
                maxlength="20"
              />
              <datalist id="habit-unit-suggestions">
                <option v-for="u in habitUnits" :key="u.value" :value="u.value" :label="`${u.value} ${u.label}`" />
              </datalist>
            </div>
            <input
              v-if="newHabitUnit"
              v-model.number="newHabitTarget"
              type="number"
              placeholder="Target"
              min="1"
              class="input-field w-24 text-sm"
            />
          </div>
          <button
            @click="createCustomHabit"
            :disabled="!newHabitName.trim() || !newHabitIcon || habitSubmitting"
            class="btn-primary w-full text-sm"
          >
            {{ habitSubmitting ? 'Creating...' : 'Create Habit' }}
          </button>
        </div>

        <!-- Habit list -->
        <div class="space-y-2">
          <div
            v-for="habit in allHabits"
            :key="habit.id"
            class="glass-card px-4 py-3 flex items-center gap-3"
            :class="!habit.is_active ? 'opacity-50' : ''"
          >
            <component :is="getIcon(habit.emoji)" :size="22" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
            <CircleDot v-else :size="22" class="text-accent flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-txt-primary">{{ habit.name }}</span>
              <div class="flex items-center gap-2">
                <span v-if="habit.unit" class="text-xs text-txt-muted">{{ habit.default_target }} {{ habit.unit }}</span>
                <span v-if="habit.is_preset" class="text-xs text-txt-muted">(preset)</span>
              </div>
            </div>
            <button
              @click="toggleHabitActive(habit)"
              class="text-xs px-2 py-1 rounded transition-colors"
              :class="habit.is_active ? 'text-amber-400 hover:bg-amber-400/10' : 'text-emerald-400 hover:bg-emerald-400/10'"
            >
              {{ habit.is_active ? 'Deactivate' : 'Activate' }}
            </button>
            <button
              v-if="resettingHabit !== habit.id"
              @click="resettingHabit = habit.id"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1"
            >
              Reset
            </button>
            <div v-else class="flex items-center gap-1 animate-fade-in">
              <button @click="resetSingleHabit(habit.id)" class="text-xs text-red-400 hover:text-red-300 font-medium px-1">Clear logs</button>
              <button @click="resettingHabit = null" class="text-xs text-txt-muted hover:text-txt-primary px-1">Cancel</button>
            </div>
            <button
              v-if="!habit.is_preset"
              @click="deleteCustomHabit(habit)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1"
            >
              Delete
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== GOALS TAB ===== -->
    <template v-if="activeTab === 'goals'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'goals', label: 'Life Goals' },
            { key: 'weekly', label: 'Weekly Targets' },
          ] as { key: GoalSubView; label: string }[]"
          :key="view.key"
          @click="goalSubView = view.key; if (view.key === 'weekly') fetchWeeklyTargets()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
          :class="goalSubView === view.key ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
        >
          {{ view.label }}
        </button>
      </div>

      <p v-if="goalError" class="text-sm text-red-400 mb-4">{{ goalError }}</p>

      <!-- ===== LIFE GOALS SUB-VIEW ===== -->
      <template v-if="goalSubView === 'goals'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">Life Goals</h2>
          <button
            @click="goalCreateMode = goalCreateMode === 'none' ? 'templates' : 'none'"
            class="text-sm text-accent hover:text-accent/80 transition-colors"
          >
            {{ goalCreateMode !== 'none' ? 'Cancel' : '+ New Goal' }}
          </button>
        </div>

        <!-- Template picker -->
        <div v-if="goalCreateMode === 'templates'" class="mb-4 space-y-3 animate-fade-in">
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="tmpl in goalTemplates.filter(t => !t.already_adopted)"
              :key="tmpl.key"
              @click="adoptTemplate(tmpl.key)"
              :disabled="templateAdopting !== null"
              class="glass-card p-3 text-left hover:border-accent/50 transition-all cursor-pointer"
            >
              <span class="text-sm font-medium text-txt-primary block">{{ tmpl.title }}</span>
              <span class="text-xs text-txt-muted mt-1 block line-clamp-2">{{ tmpl.description }}</span>
              <div v-if="tmpl.suggested_habits.length > 0" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="h in tmpl.suggested_habits"
                  :key="h"
                  class="text-[10px] bg-surface-3 text-txt-muted px-1.5 py-0.5 rounded"
                >{{ h }}</span>
              </div>
              <span v-if="templateAdopting === tmpl.key" class="text-xs text-accent mt-1 block">Creating...</span>
            </button>
          </div>
          <div class="text-center">
            <button
              @click="goalCreateMode = 'custom'"
              class="text-xs text-txt-muted hover:text-accent transition-colors"
            >
              Or create a custom goal &rarr;
            </button>
          </div>
        </div>

        <!-- Custom goal form -->
        <div v-if="goalCreateMode === 'custom'" class="glass-card p-4 mb-4 space-y-3 animate-fade-in">
          <input
            v-model="newGoalTitle"
            type="text"
            placeholder="What do you want to achieve?"
            maxlength="200"
            class="input-field"
          />
          <textarea
            v-model="newGoalDescription"
            placeholder="Description (optional)"
            maxlength="2000"
            rows="3"
            class="input-field resize-none text-sm"
          />
          <div class="flex items-center gap-2">
            <label class="text-xs text-txt-muted">Deadline:</label>
            <input
              v-model="newGoalDeadline"
              type="date"
              class="input-field flex-1 text-sm"
            />
          </div>
          <div class="flex gap-2">
            <button
              @click="createGoal"
              :disabled="!newGoalTitle.trim() || goalSubmitting"
              class="btn-primary flex-1 text-sm"
            >
              {{ goalSubmitting ? 'Creating...' : 'Create Goal' }}
            </button>
            <button
              @click="goalCreateMode = 'templates'"
              class="text-xs text-txt-muted hover:text-accent transition-colors px-3"
            >
              &larr;
            </button>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="loadingGoals" class="text-sm text-txt-muted">Loading goals...</div>

        <!-- Empty state -->
        <div v-else-if="activeGoals.length === 0 && completedGoals.length === 0" class="glass-card p-8 text-center">
          <p class="text-lg mb-2">No goals yet</p>
          <p class="text-txt-muted text-sm">Pick a template above or create a custom goal.</p>
        </div>

        <!-- Active goals -->
        <div v-else class="space-y-3">
          <div
            v-for="goal in activeGoals"
            :key="goal.id"
            class="glass-card overflow-hidden animate-slide-up"
          >
            <!-- Goal header: edit mode -->
            <div v-if="editingGoalId === goal.id" class="px-4 py-3 space-y-2">
              <input
                v-model="editGoalTitle"
                type="text"
                placeholder="Goal title"
                maxlength="200"
                class="input-field w-full text-sm font-medium"
                @keyup.enter="saveEditGoal(goal.id)"
              />
              <textarea
                v-model="editGoalDescription"
                placeholder="Description (optional)"
                maxlength="2000"
                rows="2"
                class="input-field w-full text-sm resize-none"
              />
              <div class="flex items-center gap-2">
                <label class="text-xs text-txt-muted">Deadline:</label>
                <input
                  v-model="editGoalDeadline"
                  type="date"
                  class="input-field text-sm flex-1"
                />
              </div>
              <div class="flex items-center gap-2 pt-1">
                <button
                  @click="saveEditGoal(goal.id)"
                  :disabled="!editGoalTitle.trim() || editGoalSaving"
                  class="text-xs text-accent hover:text-accent/80 disabled:opacity-40"
                >
                  {{ editGoalSaving ? 'Saving...' : 'Save' }}
                </button>
                <button @click="cancelEditGoal()" class="text-xs text-txt-muted hover:text-txt-primary">Cancel</button>
              </div>
            </div>

            <!-- Goal header: display mode -->
            <div v-else class="px-4 py-3 flex items-start gap-3 group/goal">
              <button
                @click="toggleGoalComplete(goal)"
                class="w-5 h-5 rounded-full border-2 border-bdr hover:border-accent flex-shrink-0 mt-0.5 transition-colors"
              />
              <div class="flex-1 min-w-0 cursor-pointer" @click="toggleGoalExpand(goal.id)">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-txt-primary">{{ goal.title }}</span>
                  <button
                    @click.stop="startEditGoal(goal)"
                    class="opacity-0 group-hover/goal:opacity-100 p-0.5 rounded text-txt-muted hover:text-accent transition-all"
                    title="Edit goal"
                  >
                    <Pencil :size="12" />
                  </button>
                  <span
                    v-if="goal.deadline"
                    class="text-xs px-1.5 py-0.5 rounded"
                    :class="isOverdue(goal.deadline) ? 'bg-red-500/15 text-red-400' : 'bg-surface-3 text-txt-muted'"
                  >
                    {{ new Date(goal.deadline + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}
                  </span>
                </div>
                <p v-if="goal.description" class="text-xs text-txt-muted mt-1 line-clamp-2">{{ goal.description }}</p>
                <!-- Milestone progress bar -->
                <div v-if="goal.milestone_count > 0" class="mt-2">
                  <div class="flex items-center justify-between mb-1">
                    <span class="text-xs text-txt-muted">{{ goal.milestone_done }}/{{ goal.milestone_count }} milestones</span>
                    <span class="text-xs text-txt-muted">{{ goalMilestonePct(goal) }}%</span>
                  </div>
                  <div class="w-full bg-surface-3 rounded-full h-1.5">
                    <div
                      class="h-1.5 rounded-full transition-all duration-500"
                      :class="goalMilestonePct(goal) === 100 ? 'bg-emerald-500' : 'bg-accent'"
                      :style="{ width: goalMilestonePct(goal) + '%' }"
                    />
                  </div>
                </div>
              </div>
              <button
                @click="toggleGoalExpand(goal.id)"
                class="text-txt-muted hover:text-txt-primary transition-colors text-xs px-1"
              >
                {{ expandedGoals.has(goal.id) ? '&#9650;' : '&#9660;' }}
              </button>
            </div>

            <!-- Expanded: linked habits + milestones + actions -->
            <div v-if="expandedGoals.has(goal.id)" class="border-t border-bdr px-4 py-3 space-y-3 animate-fade-in">

              <!-- Linked habits -->
              <div v-if="goal.linked_habits.length > 0" class="space-y-1.5">
                <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide">Linked Habits</p>
                <div v-for="lh in goal.linked_habits" :key="lh.habit_id" class="flex items-center gap-2 group">
                  <component :is="getIcon(lh.habit_emoji)" :size="16" class="text-accent flex-shrink-0" v-if="getIcon(lh.habit_emoji)" />
                  <CircleDot v-else :size="16" class="text-accent flex-shrink-0" />
                  <span class="text-sm text-txt-primary flex-1">{{ lh.habit_name }}</span>
                  <div class="flex gap-0.5">
                    <div
                      v-for="d in lh.days_total"
                      :key="d"
                      class="w-3 h-3 rounded-sm"
                      :class="d <= lh.days_completed ? 'bg-emerald-500' : 'bg-surface-3'"
                    />
                  </div>
                  <span class="text-xs text-txt-muted w-8 text-right">{{ lh.days_completed }}/{{ lh.days_total }}</span>
                  <button
                    @click="unlinkHabit(goal.id, lh.habit_id)"
                    class="text-xs text-txt-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 px-1"
                  >&times;</button>
                </div>
              </div>

              <!-- Link habit picker -->
              <div v-if="linkingHabitTo === goal.id" class="space-y-1.5">
                <p class="text-xs text-txt-muted">Select a habit to link:</p>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="h in availableHabitsForGoal(goal)"
                    :key="h.id"
                    @click="linkHabit(goal.id, h.id)"
                    class="text-xs bg-surface-3 hover:bg-accent/15 text-txt-primary px-2 py-1 rounded transition-colors"
                  >
                    <component :is="getIcon(h.emoji)" :size="14" class="inline-block" v-if="getIcon(h.emoji)" /><CircleDot v-else :size="14" class="inline-block" /> {{ h.name }}
                  </button>
                  <span v-if="availableHabitsForGoal(goal).length === 0" class="text-xs text-txt-muted">No unlinked habits available</span>
                </div>
              </div>

              <!-- Milestones -->
              <div v-if="goal.milestones.length > 0" class="space-y-1.5">
                <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide">Milestones</p>
                <div v-for="ms in goal.milestones" :key="ms.id" class="flex items-center gap-2 group">
                  <button
                    @click="toggleMilestone(goal.id, ms)"
                    class="w-4 h-4 rounded border flex items-center justify-center transition-all flex-shrink-0"
                    :class="ms.is_completed
                      ? 'bg-emerald-500 border-emerald-500 text-white'
                      : 'border-bdr hover:border-accent'"
                  >
                    <span v-if="ms.is_completed" class="text-[10px]">&#10003;</span>
                  </button>
                  <span
                    class="text-sm flex-1"
                    :class="ms.is_completed ? 'text-txt-muted line-through' : 'text-txt-primary'"
                  >
                    {{ ms.title }}
                  </span>
                  <button
                    @click="deleteMilestone(goal.id, ms.id)"
                    class="text-xs text-txt-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 px-1"
                  >
                    &times;
                  </button>
                </div>
              </div>

              <!-- Add milestone -->
              <div v-if="addingMilestoneTo === goal.id" class="flex gap-2 mt-2">
                <input
                  v-model="newMilestoneTitle"
                  type="text"
                  placeholder="Milestone title"
                  maxlength="200"
                  class="input-field flex-1 text-sm"
                  @keyup.enter="addMilestone(goal.id)"
                />
                <button @click="addMilestone(goal.id)" class="text-sm text-accent hover:text-accent/80">Add</button>
                <button @click="addingMilestoneTo = null; newMilestoneTitle = ''" class="text-sm text-txt-muted">Cancel</button>
              </div>

              <!-- Actions -->
              <div class="flex items-center gap-3 pt-2 border-t border-bdr/50">
                <button
                  v-if="linkingHabitTo !== goal.id"
                  @click="linkingHabitTo = goal.id"
                  class="text-xs text-accent hover:text-accent/80 transition-colors"
                >
                  + Link Habit
                </button>
                <button
                  v-else
                  @click="linkingHabitTo = null"
                  class="text-xs text-txt-muted"
                >
                  Done linking
                </button>
                <button
                  v-if="addingMilestoneTo !== goal.id"
                  @click="addingMilestoneTo = goal.id; newMilestoneTitle = ''"
                  class="text-xs text-accent hover:text-accent/80 transition-colors"
                >
                  + Add Milestone
                </button>
                <button
                  v-if="editingGoalId !== goal.id"
                  @click="startEditGoal(goal)"
                  class="text-xs text-accent hover:text-accent/80 transition-colors"
                >
                  Edit
                </button>
                <button
                  @click="deleteGoal(goal)"
                  class="text-xs text-txt-muted hover:text-red-400 transition-colors ml-auto"
                >
                  Delete Goal
                </button>
              </div>
            </div>
          </div>

          <!-- Completed goals -->
          <div v-if="completedGoals.length > 0" class="mt-6">
            <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-2">Completed</p>
            <div class="space-y-2">
              <div
                v-for="goal in completedGoals"
                :key="goal.id"
                class="glass-card px-4 py-3 flex items-center gap-3 opacity-60"
              >
                <button
                  @click="toggleGoalComplete(goal)"
                  class="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center flex-shrink-0"
                >
                  <span class="text-white text-xs">&#10003;</span>
                </button>
                <span class="text-sm text-txt-muted line-through flex-1">{{ goal.title }}</span>
                <span v-if="goal.completed_at" class="text-xs text-txt-muted">
                  {{ parseUTC(goal.completed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}
                </span>
                <button
                  @click="deleteGoal(goal)"
                  class="text-xs text-txt-muted hover:text-red-400 transition-colors px-1"
                >
                  &times;
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ===== WEEKLY TARGETS SUB-VIEW ===== -->
      <template v-if="goalSubView === 'weekly'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">Weekly Targets</h2>
          <span class="text-xs text-txt-muted">This week's progress</span>
        </div>

        <!-- Set targets prompt -->
        <div v-if="weeklyTargets.length === 0" class="glass-card p-6 text-center">
          <p class="text-sm text-txt-muted mb-2">No weekly targets set yet.</p>
          <p class="text-xs text-txt-muted">
            Go to Habits &rarr; Manage to set weekly frequency targets for your habits.
          </p>
          <!-- Quick-set targets from here -->
          <div v-if="allHabits.filter(h => h.is_active).length > 0" class="mt-4 space-y-2">
            <p class="text-xs text-txt-muted font-medium">Or set targets here:</p>
            <div
              v-for="habit in allHabits.filter(h => h.is_active)"
              :key="habit.id"
              class="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2"
            >
              <component :is="getIcon(habit.emoji)" :size="20" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
              <CircleDot v-else :size="20" class="text-accent flex-shrink-0" />
              <span class="text-sm text-txt-primary flex-1">{{ habit.name }}</span>
              <template v-if="editingTargetFor === habit.id">
                <select
                  v-model.number="editTargetValue"
                  class="input-field w-20 text-sm"
                >
                  <option :value="null">None</option>
                  <option v-for="n in 7" :key="n" :value="n">{{ n }}x/wk</option>
                </select>
                <button @click="setWeeklyTarget(habit.id)" class="text-xs text-accent">Save</button>
              </template>
              <button
                v-else
                @click="startEditTarget(habit)"
                class="text-xs text-accent hover:text-accent/80"
              >
                {{ habit.weekly_target ? habit.weekly_target + 'x/wk' : 'Set target' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Weekly targets with progress -->
        <div v-else class="space-y-3">
          <div
            v-for="item in weeklyTargets"
            :key="item.habit_id"
            class="glass-card px-4 py-3"
          >
            <div class="flex items-center gap-3 mb-2">
              <component :is="getIcon(item.habit_emoji)" :size="22" class="text-accent flex-shrink-0" v-if="getIcon(item.habit_emoji)" />
              <CircleDot v-else :size="22" class="text-accent flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <span class="text-sm font-medium text-txt-primary">{{ item.habit_name }}</span>
              </div>
              <span class="text-sm font-medium" :class="item.this_week_count >= item.weekly_target ? 'text-emerald-400' : 'text-txt-muted'">
                {{ item.this_week_count }}/{{ item.weekly_target }}
              </span>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-2">
              <div
                class="h-2 rounded-full transition-all duration-500"
                :class="item.progress_pct >= 100 ? 'bg-emerald-500' : 'bg-accent'"
                :style="{ width: Math.min(item.progress_pct, 100) + '%' }"
              />
            </div>
          </div>

          <!-- Also show habits without targets for easy setup -->
          <div
            v-if="allHabits.filter(h => h.is_active && !h.weekly_target).length > 0"
            class="mt-4"
          >
            <p class="text-xs text-txt-muted mb-2">Habits without targets:</p>
            <div class="space-y-1">
              <div
                v-for="habit in allHabits.filter(h => h.is_active && !h.weekly_target)"
                :key="habit.id"
                class="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2"
              >
                <component :is="getIcon(habit.emoji)" :size="18" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
                <CircleDot v-else :size="18" class="text-accent flex-shrink-0" />
                <span class="text-sm text-txt-muted flex-1">{{ habit.name }}</span>
                <template v-if="editingTargetFor === habit.id">
                  <select
                    v-model.number="editTargetValue"
                    class="input-field w-20 text-sm"
                  >
                    <option :value="null">None</option>
                    <option v-for="n in 7" :key="n" :value="n">{{ n }}x/wk</option>
                  </select>
                  <button @click="setWeeklyTarget(habit.id)" class="text-xs text-accent">Save</button>
                </template>
                <button
                  v-else
                  @click="startEditTarget(habit)"
                  class="text-xs text-accent hover:text-accent/80"
                >
                  Set target
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== MEDITATE TAB ===== -->
    <template v-if="activeTab === 'meditate'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'new', label: 'New Session' },
            { key: 'history', label: 'History' },
          ] as { key: MedView; label: string }[]"
          :key="view.key"
          @click="medView = view.key; if (view.key === 'history') fetchMedSessions()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
          :class="medView === view.key || (medView === 'player' && view.key === 'new')
            ? 'bg-accent/15 text-accent'
            : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
        >
          {{ view.label }}
        </button>
        <span v-if="medRemaining" class="ml-auto text-xs text-txt-muted self-center">
          {{ medRemaining.remaining }}/{{ medRemaining.limit }} sessions left today
        </span>
      </div>

      <p v-if="medError" class="text-sm text-red-400 mb-4">{{ medError }}</p>

      <!-- ===== NEW SESSION VIEW ===== -->
      <template v-if="medView === 'new'">
        <!-- Type picker -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-3">Choose a meditation type</h3>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="mt in meditationTypes"
              :key="mt.key"
              @click="medType = mt.key"
              class="glass-card px-4 py-3 text-left transition-all duration-150"
              :class="medType === mt.key ? 'ring-1 ring-accent bg-accent/5' : 'hover:bg-surface-2'"
            >
              <div class="flex items-center gap-2 mb-1">
                <component :is="meditationTypeIcons[mt.key]" :size="20" v-if="meditationTypeIcons[mt.key]" />
                <span class="text-sm font-medium text-txt-primary">{{ mt.label }}</span>
              </div>
              <p class="text-xs text-txt-muted">{{ mt.desc }}</p>
            </button>
          </div>
        </div>

        <!-- Length -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-3">Length</h3>
          <div class="flex gap-2">
            <button
              v-for="opt in lengthOptions"
              :key="opt.key"
              @click="medLength = opt.key"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medLength === opt.key
                ? 'bg-accent text-white'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>

        <!-- Ambience -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-3">Ambience</h3>
          <div class="flex gap-2">
            <button
              v-for="a in ambienceOptions"
              :key="a.key"
              @click="medAmbience = a.key"
              class="flex-1 py-2.5 rounded-lg text-center transition-all duration-150"
              :class="medAmbience === a.key
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              <component :is="ambienceIcons[a.key]" :size="20" class="mx-auto" v-if="ambienceIcons[a.key]" />
              <span class="text-xs block mt-1">{{ a.label }}</span>
            </button>
          </div>
        </div>

        <!-- Voice -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-3">Voice</h3>
          <div class="flex gap-2">
            <button
              @click="medVoice = 'serene'"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medVoice === 'serene'
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              Serene
              <span class="block text-xs opacity-70">Calm &amp; soothing</span>
            </button>
            <button
              @click="medVoice = 'gentle'"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medVoice === 'gentle'
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              Gentle
              <span class="block text-xs opacity-70">Warm &amp; nurturing</span>
            </button>
            <button
              @click="medVoice = 'whisper'"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medVoice === 'whisper'
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              Whisper
              <span class="block text-xs opacity-70">Soft &amp; breathy</span>
            </button>
          </div>
        </div>

        <!-- Focus (optional) -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-2">Focus <span class="text-txt-muted font-normal">(optional)</span></h3>
          <input
            v-model="medFocus"
            type="text"
            placeholder="e.g. letting go of work stress, sleep preparation..."
            maxlength="200"
            class="input-field text-sm"
          />
        </div>

        <!-- Generate button -->
        <button
          @click="generateMeditation"
          :disabled="medGenerating || (medRemaining && medRemaining.remaining <= 0)"
          class="btn-primary w-full py-3"
        >
          <span v-if="medGenerating" class="inline-flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            {{ medGenStage || 'Starting...' }}
          </span>
          <span v-else-if="medRemaining && medRemaining.remaining <= 0">
            No sessions remaining today
          </span>
          <span v-else>Generate Meditation</span>
        </button>
      </template>

      <!-- ===== PLAYER VIEW ===== -->
      <template v-if="medView === 'player' && medSession">
        <!-- Back button -->
        <button @click="goToNewMeditation" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-4">&larr;</button>

        <!-- Session card -->
        <div class="glass-card p-6 mb-4">
          <div class="flex items-start justify-between mb-3">
            <div>
              <h2 class="text-lg font-semibold text-txt-primary">{{ medSession.title }}</h2>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs text-txt-muted">{{ getMedTypeLabel(medSession.type) }}</span>
                <span class="text-xs text-txt-muted">{{ Math.floor(medSession.duration_seconds / 60) }}:{{ String(medSession.duration_seconds % 60).padStart(2, '0') }}</span>
                <span class="text-xs text-txt-muted">${{ medSession.cost.toFixed(4) }}</span>
              </div>
            </div>
            <button
              @click="toggleMedFavorite"
              class="text-xl transition-colors"
              :class="medSession.is_favorite ? 'text-amber-400' : 'text-txt-muted hover:text-amber-400'"
            >
              {{ medSession.is_favorite ? '&#9733;' : '&#9734;' }}
            </button>
          </div>

          <!-- Audio controls -->
          <div class="space-y-3">
            <!-- Play/pause + progress -->
            <div class="flex items-center gap-3">
              <button
                @click="togglePlayPause()"
                class="w-10 h-10 rounded-full bg-accent text-white flex items-center justify-center hover:bg-accent/80 transition-colors flex-shrink-0"
              >
                <span v-if="medPlaying" class="text-sm">&#9646;&#9646;</span>
                <span v-else class="text-sm ml-0.5">&#9654;</span>
              </button>
              <div class="flex-1">
                <div
                  @click="seekAudio"
                  class="w-full h-2 bg-surface-3 rounded-full cursor-pointer relative"
                >
                  <div
                    class="h-2 rounded-full bg-accent transition-all duration-200"
                    :style="{ width: medProgress + '%' }"
                  />
                </div>
                <div class="flex justify-between mt-1">
                  <span class="text-xs text-txt-muted">{{ medFormatTime(medCurrentTime) }}</span>
                  <span class="text-xs text-txt-muted">{{ medDurationSec > 0 ? medFormatTime(medDurationSec) : '--:--' }}</span>
                </div>
              </div>
            </div>

            <!-- Ambient volume (if not silence) -->
            <div v-if="medSession.ambience !== 'silence'" class="flex items-center gap-3">
              <span class="text-xs text-txt-muted w-20">Ambience</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                :value="medAmbientVolume"
                @input="updateAmbientVolume(parseFloat(($event.target as HTMLInputElement).value))"
                class="flex-1 accent-accent h-1"
              />
              <span class="text-xs text-txt-muted w-8 text-right">{{ Math.round(medAmbientVolume * 100) }}%</span>
            </div>
          </div>
        </div>

        <!-- Live transcript -->
        <div class="glass-card p-5 mb-4 max-h-64 overflow-y-auto">
          <h3 class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-3">Transcript</h3>
          <div class="space-y-3">
            <p
              v-for="(para, i) in transcriptParagraphs"
              :key="i"
              class="text-sm leading-relaxed transition-all duration-500"
              :class="i <= activeParagraphIndex
                ? 'text-txt-secondary'
                : 'text-txt-muted/40'"
            >
              {{ para }}
            </p>
          </div>
        </div>

        <!-- Post-session mood removed — cluttered the meditation experience -->
      </template>

      <!-- ===== HISTORY VIEW ===== -->
      <template v-if="medView === 'history'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">Past Sessions</h2>
          <button
            @click="medShowFavoritesOnly = !medShowFavoritesOnly"
            class="text-sm transition-colors"
            :class="medShowFavoritesOnly ? 'text-amber-400' : 'text-txt-muted hover:text-txt-primary'"
          >
            {{ medShowFavoritesOnly ? '&#9733; Favorites' : '&#9734; All' }}
          </button>
        </div>

        <div v-if="loadingMeditation" class="text-sm text-txt-muted">Loading...</div>
        <div v-else-if="filteredMedSessions.length === 0" class="glass-card p-8 text-center">
          <p class="text-lg mb-2">{{ medShowFavoritesOnly ? 'No favorites yet' : 'No sessions yet' }}</p>
          <p class="text-txt-muted text-sm">{{ medShowFavoritesOnly ? 'Star a session to save it here.' : 'Generate your first meditation to get started.' }}</p>
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="s in filteredMedSessions"
            :key="s.id"
            @click="openMedSession(s.id)"
            class="glass-card px-4 py-3 w-full text-left flex items-start gap-3 transition-colors hover:bg-surface-2 cursor-pointer"
          >
            <component :is="meditationTypeIcons[s.type]" :size="22" class="text-accent flex-shrink-0 mt-0.5" v-if="meditationTypeIcons[s.type]" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-txt-primary truncate">{{ s.title }}</span>
                <span class="text-xs text-txt-muted flex-shrink-0">{{ timeAgo(s.created_at) }}</span>
              </div>
              <div class="flex items-center gap-2 mt-0.5">
                <span class="text-xs text-txt-muted">{{ getMedTypeLabel(s.type) }}</span>
                <span class="text-xs text-txt-muted">{{ Math.floor(s.duration_seconds / 60) }}:{{ String(s.duration_seconds % 60).padStart(2, '0') }}</span>
                <span v-if="s.mood_after" class="text-sm">{{ s.mood_after }}</span>
                <span v-if="s.is_favorite" class="text-amber-400 text-xs">&#9733;</span>
              </div>
            </div>
            <button
              @click.stop="deleteMedSession(s.id)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-1 self-center"
            >
              &times;
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== THERAPIST TAB ===== -->
    <template v-if="activeTab === 'therapist'">
      <!-- Unavailable state -->
      <div v-if="!therapistAvailable" class="glass-card p-8 text-center">
        <AlertTriangle :size="32" class="mx-auto mb-3 text-amber-400" />
        <h3 class="text-lg font-semibold text-txt-primary mb-2">Therapist Unavailable</h3>
        <p class="text-sm text-txt-muted">Venice AI is currently unreachable. Please try again later.</p>
        <button @click="fetchTherapistStatus()" class="mt-4 px-4 py-2 text-sm rounded-lg bg-accent/15 text-accent hover:bg-accent/25 transition-colors">
          Retry Connection
        </button>
      </div>

      <template v-else>
        <!-- Sub-nav -->
        <div class="flex gap-3 mb-6">
          <button
            v-for="view in [
              { key: 'chat', label: 'Chat' },
              { key: 'notes', label: 'Session Notes' },
            ] as { key: TherapistView; label: string }[]"
            :key="view.key"
            @click="therapistView = view.key as TherapistView; if (view.key === 'notes') fetchTherapistNotes()"
            class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
            :class="therapistView === view.key || (therapistView === 'note-detail' && view.key === 'notes')
              ? 'bg-accent/15 text-accent'
              : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
          >
            {{ view.label }}
          </button>
          <span v-if="therapistStatus" class="ml-auto text-xs text-txt-muted self-center">
            {{ therapistStatus.sessions_remaining }}/{{ therapistStatus.sessions_limit }} sessions left today
          </span>
        </div>

        <p v-if="therapistError" class="text-sm text-red-400 mb-4">{{ therapistError }}</p>

        <!-- ===== CHAT VIEW ===== -->
        <template v-if="therapistView === 'chat'">
          <!-- Pre-session: start button -->
          <div v-if="!therapistSessionActive" class="space-y-4">
            <!-- Disclaimer -->
            <div v-if="therapistDisclaimer" class="glass-card p-4 border border-amber-500/20">
              <div class="flex items-start gap-2">
                <AlertTriangle :size="16" class="text-amber-400 mt-0.5 shrink-0" />
                <p class="text-xs text-txt-muted leading-relaxed">{{ therapistDisclaimer }}</p>
              </div>
            </div>

            <div class="glass-card p-8 text-center">
              <MessageCircleHeart :size="40" class="mx-auto mb-4 text-accent" />
              <h3 class="text-lg font-semibold text-txt-primary mb-2">Ready to talk?</h3>
              <p class="text-sm text-txt-muted mb-6 max-w-md mx-auto">
                A private space to reflect, process, and explore what's on your mind.
                Powered by Venice AI — your data stays private.
              </p>
              <button
                @click="startTherapistSession()"
                :disabled="therapistStatus?.sessions_remaining === 0"
                class="px-6 py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {{ therapistStatus?.sessions_remaining === 0 ? 'No sessions left today' : 'Start Session' }}
              </button>
            </div>
          </div>

          <!-- Active session: chat -->
          <div v-else class="flex flex-col" style="height: calc(100vh - 300px); min-height: 400px;">
            <!-- Messages -->
            <div class="flex-1 overflow-y-auto space-y-4 mb-4 pr-1" ref="chatContainer">
              <div
                v-for="(msg, i) in therapistMessages"
                :key="i"
                class="flex"
                :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
              >
                <div
                  class="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed"
                  :class="msg.role === 'user'
                    ? 'bg-accent text-white rounded-br-md'
                    : 'glass-card text-txt-primary rounded-bl-md'"
                >
                  <p v-for="(para, j) in msg.content.split('\n\n')" :key="j" :class="j > 0 ? 'mt-2' : ''" v-html="renderMarkdown(para)">
                  </p>
                  <!-- Regenerate greeting button — only on the first assistant message before user replies -->
                  <button
                    v-if="i === 0 && msg.role === 'assistant' && therapistMessages.length <= 1"
                    @click="regenerateTherapistGreeting()"
                    :disabled="therapistRegeneratingGreeting"
                    class="mt-2 flex items-center gap-1 text-xs text-txt-secondary hover:text-accent transition-colors disabled:opacity-40"
                    title="Regenerate greeting"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="therapistRegeneratingGreeting ? 'animate-spin' : ''"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
                    {{ therapistRegeneratingGreeting ? 'Regenerating...' : 'Regenerate' }}
                  </button>
                </div>
              </div>

              <!-- Typing indicator -->
              <div v-if="therapistSending" class="flex justify-start">
                <div class="glass-card rounded-2xl rounded-bl-md px-4 py-3">
                  <div class="flex gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-txt-muted animate-bounce" style="animation-delay: 0ms"></span>
                    <span class="w-2 h-2 rounded-full bg-txt-muted animate-bounce" style="animation-delay: 150ms"></span>
                    <span class="w-2 h-2 rounded-full bg-txt-muted animate-bounce" style="animation-delay: 300ms"></span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Input area -->
            <div class="border-t border-bdr pt-3">
              <div class="flex items-center gap-2 mb-2">
                <button
                  @click="endTherapistSession()"
                  :disabled="therapistEndingSession"
                  class="ml-auto px-3 py-1.5 text-xs rounded-lg border border-bdr text-txt-muted hover:text-txt-primary hover:bg-surface-2 transition-colors disabled:opacity-40"
                >
                  {{ therapistEndingSession ? 'Saving...' : 'End Session' }}
                </button>
              </div>
              <div class="flex gap-2">
                <textarea
                  v-model="therapistInput"
                  @keydown.enter.exact.prevent="sendTherapistMessage()"
                  placeholder="What's on your mind..."
                  rows="2"
                  class="flex-1 bg-surface-2 border border-bdr rounded-xl px-4 py-3 text-sm text-txt-primary placeholder-txt-muted resize-none focus:outline-none focus:ring-1 focus:ring-accent/50"
                  :disabled="therapistSending || therapistMessagesRemaining <= 0"
                ></textarea>
                <button
                  @click="sendTherapistMessage()"
                  :disabled="!therapistInput.trim() || therapistSending || therapistMessagesRemaining <= 0"
                  class="self-end px-4 py-3 rounded-xl bg-accent text-white hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Send :size="18" />
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- ===== NOTES LIST VIEW ===== -->
        <template v-if="therapistView === 'notes'">
          <div v-if="therapistNotes.length === 0" class="glass-card p-8 text-center">
            <ScrollText :size="32" class="mx-auto mb-3 text-txt-muted" />
            <p class="text-sm text-txt-muted">No session notes yet. Complete a session to see notes here.</p>
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="note in therapistNotes"
              :key="note.id"
              @click="viewTherapistNote(note)"
              class="glass-card p-4 cursor-pointer hover:bg-surface-2 transition-colors group"
            >
              <div class="flex items-start justify-between mb-2">
                <div>
                  <p class="text-sm font-medium text-txt-primary">{{ note.themes.split('\n')[0] }}</p>
                  <p class="text-xs text-txt-muted mt-0.5">{{ formatDate(note.created_at) }}</p>
                </div>
                <button
                  @click.stop="deleteTherapistNote(note.id)"
                  class="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-txt-muted hover:text-red-400 hover:bg-red-400/10 transition-all"
                  title="Delete note"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
              <div v-if="note.mood_snapshot" class="flex items-center gap-1.5 mb-2">
                <span class="text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent">{{ note.mood_snapshot }}</span>
              </div>
              <p v-if="note.follow_up" class="text-xs text-txt-muted line-clamp-2">{{ note.follow_up }}</p>
              <div class="flex items-center gap-3 mt-2 text-xs text-txt-muted">
                <span>{{ note.message_count }} messages</span>
                <span>${{ note.cost.toFixed(4) }}</span>
              </div>
            </div>
          </div>
        </template>

        <!-- ===== NOTE DETAIL VIEW ===== -->
        <template v-if="therapistView === 'note-detail' && therapistCurrentNote">
          <button
            @click="therapistView = 'notes'; therapistEditingNote = false"
            class="text-sm text-accent hover:underline mb-4 inline-block"
          >
            &larr;
          </button>

          <div class="glass-card p-6 space-y-5">
            <div class="flex items-start justify-between">
              <div>
                <p class="text-xs text-txt-muted">{{ formatDate(therapistCurrentNote.created_at) }}</p>
                <div v-if="therapistCurrentNote.mood_snapshot" class="mt-1">
                  <span class="text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent">{{ therapistCurrentNote.mood_snapshot }}</span>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  v-if="!therapistEditingNote"
                  @click="startEditingNote()"
                  class="p-1.5 rounded-lg text-txt-muted hover:text-accent hover:bg-accent/10 transition-colors"
                  title="Edit note"
                >
                  <Pencil :size="16" />
                </button>
                <button
                  @click="deleteTherapistNote(therapistCurrentNote.id)"
                  class="p-1.5 rounded-lg text-txt-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                  title="Delete note"
                >
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>

            <!-- View mode -->
            <template v-if="!therapistEditingNote">
              <div>
                <h4 class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5">Themes</h4>
                <p class="text-sm text-txt-primary whitespace-pre-line">{{ therapistCurrentNote.themes }}</p>
              </div>
              <div v-if="therapistCurrentNote.patterns">
                <h4 class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5">Patterns</h4>
                <p class="text-sm text-txt-primary whitespace-pre-line">{{ therapistCurrentNote.patterns }}</p>
              </div>
              <div v-if="therapistCurrentNote.follow_up">
                <h4 class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5">Follow-up</h4>
                <p class="text-sm text-txt-primary whitespace-pre-line">{{ therapistCurrentNote.follow_up }}</p>
              </div>
            </template>

            <!-- Edit mode -->
            <template v-else>
              <div>
                <label class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5 block">Themes</label>
                <textarea v-model="therapistEditThemes" rows="3" class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary resize-none focus:outline-none focus:ring-1 focus:ring-accent/50"></textarea>
              </div>
              <div>
                <label class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5 block">Patterns</label>
                <textarea v-model="therapistEditPatterns" rows="3" class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary resize-none focus:outline-none focus:ring-1 focus:ring-accent/50"></textarea>
              </div>
              <div>
                <label class="text-xs font-semibold text-txt-muted uppercase tracking-wider mb-1.5 block">Follow-up</label>
                <textarea v-model="therapistEditFollowUp" rows="3" class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary resize-none focus:outline-none focus:ring-1 focus:ring-accent/50"></textarea>
              </div>
              <div class="flex gap-2 justify-end">
                <button @click="therapistEditingNote = false" class="px-3 py-1.5 text-sm rounded-lg text-txt-muted hover:text-txt-primary transition-colors">
                  Cancel
                </button>
                <button @click="saveNoteEdit()" class="px-4 py-1.5 text-sm rounded-lg bg-accent text-white hover:bg-accent/90 transition-colors">
                  Save
                </button>
              </div>
            </template>

            <div class="flex items-center gap-3 pt-3 border-t border-bdr text-xs text-txt-muted">
              <span>{{ therapistCurrentNote.message_count }} messages</span>
              <span>{{ therapistCurrentNote.provider }}</span>
              <span>${{ therapistCurrentNote.cost.toFixed(4) }}</span>
            </div>
          </div>
        </template>
      </template>
    </template>

    <!-- ===== JOURNAL TAB ===== -->
    <template v-if="activeTab === 'journal'">
      <template v-if="journalView === 'list'">
        <div class="flex items-center justify-between mb-6">
          <p class="text-sm text-txt-secondary">Write, reflect, understand.</p>
          <button @click="goToCompose" class="btn-primary px-5 py-2 text-sm">New Entry</button>
        </div>
        <div v-if="loadingJournal" class="text-sm text-txt-muted">Loading...</div>
        <div v-else-if="journalEntries.length === 0" class="glass-card p-8 text-center">
          <p class="text-lg mb-2">No entries yet</p>
          <p class="text-txt-muted text-sm">Start writing to capture your thoughts.</p>
        </div>
        <div v-else class="space-y-5">
          <div v-for="group in groupedJournalEntries" :key="group.label">
            <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-2">{{ group.label }}</p>
            <div class="space-y-2">
              <button
                v-for="entry in group.entries"
                :key="entry.id"
                @click="goToDetail(entry.id)"
                class="glass-card px-4 py-3 w-full text-left flex items-start gap-3 animate-slide-up transition-colors hover:bg-surface-2"
              >
                <component :is="moodIcons[entry.mood_emoji]" v-if="entry.mood_emoji && moodIcons[entry.mood_emoji]" :size="24" class="text-accent flex-shrink-0" />
                <Meh v-else-if="entry.mood_emoji" :size="24" class="text-accent flex-shrink-0" />
                <BookOpen v-else :size="24" class="text-txt-muted flex-shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-txt-primary truncate">{{ entry.title || entry.content_preview.slice(0, 60) }}</span>
                    <span class="text-xs text-txt-muted flex-shrink-0">{{ timeAgo(entry.created_at) }}</span>
                  </div>
                  <p v-if="entry.title" class="text-sm text-txt-secondary mt-0.5 truncate">{{ entry.content_preview }}</p>
                  <div v-if="entry.reflection_count > 0" class="flex items-center gap-1 mt-1">
                    <span class="text-xs text-accent">{{ entry.reflection_count }} reflection{{ entry.reflection_count > 1 ? 's' : '' }}</span>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>
      </template>

      <template v-if="journalView === 'compose'">
        <div class="mb-6">
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr;</button>
          <h2 class="text-xl font-bold text-txt-primary">New Entry</h2>
        </div>
        <div class="glass-card p-6 space-y-4">
          <input v-model="composeTitle" type="text" placeholder="Title (optional)" maxlength="200" class="input-field text-lg font-medium" />
          <textarea v-model="composeContent" placeholder="What's on your mind?" maxlength="50000" rows="10" class="input-field resize-none text-sm leading-relaxed" />
          <p v-if="contentLength > 0" class="text-right text-xs" :class="contentLength > 45000 ? 'text-amber-400' : 'text-txt-muted'">{{ contentLength.toLocaleString() }}/50,000</p>
          <div>
            <p class="text-xs text-txt-muted mb-2">How are you feeling? (optional)</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="mood in moods"
                :key="mood.emoji"
                @click="composeMood = composeMood === mood.emoji ? null : mood.emoji"
                class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
                :class="composeMood === mood.emoji ? 'bg-accent/15 ring-1 ring-accent/50 text-accent' : 'text-txt-muted hover:bg-surface-3 hover:text-txt-primary'"
                :title="mood.label"
              >
                <component :is="moodIcons[mood.emoji]" :size="20" v-if="moodIcons[mood.emoji]" />
              </button>
            </div>
            <p v-if="composeMoodLabel" class="text-xs text-accent mt-1.5 animate-fade-in">{{ composeMoodLabel }}</p>
          </div>
          <p v-if="journalError" class="text-sm text-red-400">{{ journalError }}</p>
          <button @click="saveEntry" :disabled="!composeContent.trim() || journalSubmitting" class="btn-primary w-full">
            <span v-if="journalSubmitting" class="inline-flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Saving...
            </span>
            <span v-else>Save Entry</span>
          </button>
        </div>
      </template>

      <template v-if="journalView === 'detail'">
        <div class="mb-6">
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr;</button>
          <h2 class="text-xl font-bold text-txt-primary">Entry</h2>
        </div>
        <div v-if="loadingDetail" class="text-sm text-txt-muted">Loading...</div>
        <template v-else-if="currentEntry">
          <div class="glass-card p-6 mb-6">
            <div class="flex items-start justify-between mb-4">
              <div>
                <h2 v-if="currentEntry.title" class="text-lg font-semibold text-txt-primary mb-1">{{ currentEntry.title }}</h2>
                <div class="flex items-center gap-2 text-xs text-txt-muted">
                  <span>{{ formatDate(currentEntry.created_at) }}</span>
                  <span v-if="currentEntry.mood_emoji" class="flex items-center gap-1">
                    <component :is="moodIcons[currentEntry.mood_emoji]" :size="14" class="text-accent" v-if="moodIcons[currentEntry.mood_emoji]" />
                    <Meh v-else :size="14" class="text-accent" />
                    <span>{{ currentEntry.mood_label }}</span>
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <div class="relative">
                  <button @click="showExportMenu = !showExportMenu" class="text-xs text-txt-muted hover:text-accent transition-colors px-2 py-1 flex items-center gap-1">
                    <Download :size="12" />
                    Export
                  </button>
                  <div v-if="showExportMenu" class="absolute right-0 top-full mt-1 glass-card p-1 rounded-lg shadow-lg z-20 min-w-[140px]">
                    <button @click="exportEntry('markdown')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-white/5 px-3 py-2 rounded transition-colors">
                      Markdown (.md)
                    </button>
                    <button @click="exportEntry('json')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-white/5 px-3 py-2 rounded transition-colors">
                      JSON (.json)
                    </button>
                  </div>
                </div>
                <button @click="deleteEntry" class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1">Delete</button>
              </div>
            </div>
            <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ currentEntry.content }}</p>
          </div>
          <div class="mb-6">
            <h3 class="text-sm font-semibold text-txt-primary mb-3">
              AI Reflections
              <span v-if="currentEntry.reflections.length > 0" class="text-txt-muted font-normal">({{ currentEntry.reflections.length }}/3)</span>
            </h3>
            <div v-if="currentEntry.reflections.length === 0" class="glass-card p-5 text-center">
              <p class="text-sm text-txt-muted mb-1">No reflections yet.</p>
              <p class="text-xs text-txt-muted">Get an AI-generated follow-up question to deepen your thinking.</p>
            </div>
            <div v-else class="space-y-3">
              <div v-for="(reflection, i) in currentEntry.reflections" :key="reflection.id" class="glass-card p-4 animate-slide-up">
                <div class="flex items-center gap-2 mb-2">
                  <span class="text-xs font-medium text-accent">Reflection {{ i + 1 }}</span>
                  <span class="text-xs text-txt-muted">{{ formatDate(reflection.created_at) }}</span>
                  <span class="text-xs text-txt-muted ml-auto">${{ reflection.cost.toFixed(4) }}</span>
                </div>
                <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ reflection.content }}</p>
              </div>
            </div>
          </div>
          <button v-if="reflectionsRemaining > 0" @click="requestReflection" :disabled="reflecting" class="btn-primary w-full">
            <span v-if="reflecting" class="inline-flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Reflecting...
            </span>
            <span v-else>Get AI Reflection <span class="text-xs opacity-70">({{ reflectionsRemaining }} remaining)</span></span>
          </button>
          <p v-else class="text-xs text-txt-muted text-center">Maximum reflections reached for this entry.</p>
          <p v-if="journalError" class="text-sm text-red-400 mt-3">{{ journalError }}</p>
        </template>
        <div v-else class="glass-card p-6 text-center">
          <p v-if="journalError" class="text-sm text-red-400">{{ journalError }}</p>
          <p v-else class="text-sm text-txt-muted">Entry not found.</p>
        </div>
      </template>
    </template>

    <!-- Therapist session leave warning -->
    <transition name="fade">
      <div v-if="showTherapistLeaveWarning" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div class="bg-surface-1 border border-white/[0.08] rounded-2xl p-6 max-w-sm mx-4 shadow-xl">
          <div class="flex items-center gap-3 mb-3">
            <AlertTriangle class="w-5 h-5 text-amber-400 shrink-0" />
            <h3 class="text-lg font-semibold text-txt-primary">Active session</h3>
          </div>
          <p class="text-sm text-txt-secondary mb-5">
            You have an active therapy session. Leaving will reset it and your conversation will be lost.
          </p>
          <div class="flex gap-3 justify-end">
            <button
              @click="cancelTherapistLeave"
              class="px-4 py-2 text-sm font-medium text-txt-secondary hover:text-txt-primary rounded-lg border border-white/[0.08] hover:bg-surface-2 transition-colors"
            >
              Stay
            </button>
            <button
              @click="confirmTherapistLeave"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-500 rounded-lg transition-colors"
            >
              Leave &amp; reset
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Settings panel overlay -->
    <transition name="fade">
      <SettingsPanel v-if="showSettings" @close="showSettings = false" />
    </transition>
    </div>
  </div>
</template>

<style scoped>
.badge-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgba(255 255 255 / 0.12) transparent;
}
.badge-scroll::-webkit-scrollbar {
  height: 4px;
}
.badge-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.badge-scroll::-webkit-scrollbar-thumb {
  background: rgba(255 255 255 / 0.12);
  border-radius: 9999px;
}
.badge-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255 255 255 / 0.25);
}

/* Prestige animations */
.prestige-glow {
  box-shadow: 0 0 12px rgba(168, 85, 247, 0.3), 0 0 4px rgba(245, 158, 11, 0.2);
}

.prestige-star {
  animation: star-twinkle 2s ease-in-out infinite;
}
.prestige-star:nth-child(2) { animation-delay: 0.4s; }
.prestige-star:nth-child(3) { animation-delay: 0.8s; }
.prestige-star:nth-child(4) { animation-delay: 1.2s; }
.prestige-star:nth-child(5) { animation-delay: 1.6s; }

@keyframes star-twinkle {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.3); }
}

.multiplier-pulse {
  animation: mult-pulse 2.5s ease-in-out infinite;
}

@keyframes mult-pulse {
  0%, 100% { opacity: 0.85; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.08); }
}

.prestige-bar-shimmer {
  background-size: 200% 100%;
  animation: bar-shimmer 2s linear infinite;
}

@keyframes bar-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.prestige-banner-glow {
  animation: banner-glow 3s ease-in-out infinite;
}

@keyframes banner-glow {
  0%, 100% { box-shadow: 0 0 8px rgba(168, 85, 247, 0.1); }
  50% { box-shadow: 0 0 20px rgba(168, 85, 247, 0.25), 0 0 8px rgba(245, 158, 11, 0.15); }
}
</style>
