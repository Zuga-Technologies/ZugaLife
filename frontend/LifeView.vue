<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, ApiError } from '@core/api/client'

// --- Tabs ---

type Tab = 'journal' | 'habits'
const activeTab = ref<Tab>('journal')

// ============================
// MOOD EMOJI DEFINITIONS (shared by journal compose)
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
    const res = await api.post<JournalEntryFull>('/api/life/journal', {
      title: composeTitle.value.trim() || null,
      content: composeContent.value.trim(),
      mood_emoji: composeMood.value,
    })
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
const newHabitEmoji = ref('')
const newHabitUnit = ref<string | null>(null)
const newHabitTarget = ref<number | null>(null)
const showNewHabitForm = ref(false)

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
      // Uncheck
      const today = new Date().toISOString().split('T')[0]
      await api.delete(`/api/life/habits/log/${item.habit.id}/${today}`)
    } else {
      // Check
      const amt = amountInputs.value[item.habit.id]
      await api.post('/api/life/habits/log', {
        habit_id: item.habit.id,
        completed: true,
        amount: amt ? parseFloat(amt) : null,
      })
    }
    await fetchHabitCheckin()
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
  if (!newHabitName.value.trim() || !newHabitEmoji.value.trim() || habitSubmitting.value) return

  habitSubmitting.value = true
  habitError.value = null

  try {
    await api.post('/api/life/habits', {
      name: newHabitName.value.trim(),
      emoji: newHabitEmoji.value.trim(),
      unit: newHabitUnit.value || null,
      default_target: newHabitTarget.value || null,
    })
    newHabitName.value = ''
    newHabitEmoji.value = ''
    newHabitUnit.value = null
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
  { value: 'hours', label: 'Hours' },
  { value: 'minutes', label: 'Minutes' },
  { value: 'glasses', label: 'Glasses' },
  { value: 'steps', label: 'Steps' },
  { value: 'servings', label: 'Servings' },
  { value: 'pages', label: 'Pages' },
  { value: 'count', label: 'Count' },
]

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

// --- Init ---

onMounted(async () => {
  await Promise.all([
    fetchJournalEntries(),
    fetchHabitCheckin(), fetchHabitStreaks(), fetchAllHabits(),
  ])
  loadingJournal.value = false
  loadingHabits.value = false
})
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-10 animate-fade-in">

    <!-- Success Toasts -->
    <transition name="fade">
      <div
        v-if="journalSuccess || habitSuccess"
        class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-6 py-3 rounded-lg bg-emerald-600 text-white font-medium text-sm shadow-lg"
      >
        {{ journalSuccess || habitSuccess }}
      </div>
    </transition>

    <!-- Header + Streak -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-txt-primary">ZugaLife</h1>
        <p class="text-sm text-txt-secondary mt-1">Track, reflect, understand.</p>
      </div>
      <div
        v-if="habitStreaks && habitStreaks.overall_current > 0"
        class="glass-card px-4 py-2 flex items-center gap-2"
      >
        <span class="text-lg">🔥</span>
        <div>
          <p class="text-sm font-semibold text-txt-primary">{{ habitStreaks.overall_current }}-day streak</p>
          <p class="text-xs text-txt-muted">Best: {{ habitStreaks.overall_longest }} days</p>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-6 border-b border-bdr">
      <button
        @click="activeTab = 'journal'"
        class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
        :class="activeTab === 'journal'
          ? 'text-accent border-accent'
          : 'text-txt-muted border-transparent hover:text-txt-primary'"
      >
        Journal
      </button>
      <button
        @click="activeTab = 'habits'"
        class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
        :class="activeTab === 'habits'
          ? 'text-accent border-accent'
          : 'text-txt-muted border-transparent hover:text-txt-primary'"
      >
        Habits
      </button>
    </div>

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
              <span class="text-xl flex-shrink-0">{{ item.habit.emoji }}</span>
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
                  class="w-16 px-2 py-1 text-sm text-right rounded-md bg-surface-3 text-txt-primary border border-bdr focus:border-accent focus:outline-none"
                />
                <span class="text-xs text-txt-muted">{{ item.habit.unit }}</span>
              </div>
            </div>
          </div>

          <!-- Streaks summary -->
          <div v-if="habitStreaks && habitStreaks.overall_current > 0" class="glass-card p-4 mt-6 flex items-center gap-3">
            <span class="text-lg">&#x1F525;</span>
            <div>
              <p class="text-sm font-semibold text-txt-primary">{{ habitStreaks.overall_current }}-day habit streak</p>
              <p class="text-xs text-txt-muted">Longest: {{ habitStreaks.overall_longest }} days</p>
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
              <span v-for="(emoji, i) in day.habits_done" :key="i" class="text-sm">{{ emoji }}</span>
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
          <div class="flex gap-2">
            <input
              v-model="newHabitEmoji"
              type="text"
              placeholder="Emoji"
              maxlength="4"
              class="input-field w-16 text-center text-lg"
            />
            <input
              v-model="newHabitName"
              type="text"
              placeholder="Habit name"
              maxlength="50"
              class="input-field flex-1"
            />
          </div>
          <div class="flex gap-2">
            <select
              v-model="newHabitUnit"
              class="input-field flex-1 text-sm"
            >
              <option :value="null">No unit (checkbox)</option>
              <option v-for="u in habitUnits" :key="u.value" :value="u.value">{{ u.label }}</option>
            </select>
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
            :disabled="!newHabitName.trim() || !newHabitEmoji.trim() || habitSubmitting"
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
            <span class="text-xl">{{ habit.emoji }}</span>
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
                <span v-if="entry.mood_emoji" class="text-2xl flex-shrink-0">{{ entry.mood_emoji }}</span>
                <span v-else class="text-2xl flex-shrink-0 text-txt-muted">📝</span>
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
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr; Back</button>
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
                class="px-2 py-1 rounded-lg text-sm transition-all duration-150"
                :class="composeMood === mood.emoji ? 'bg-accent/15 ring-1 ring-accent/50' : 'hover:bg-surface-3'"
              >
                <span>{{ mood.emoji }}</span>
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
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr; Back</button>
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
                    <span>{{ currentEntry.mood_emoji }}</span>
                    <span>{{ currentEntry.mood_label }}</span>
                  </span>
                </div>
              </div>
              <button @click="deleteEntry" class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1">Delete</button>
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

  </div>
</template>
