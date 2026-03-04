<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, ApiError } from '@core/api/client'

// --- Tabs ---

type Tab = 'mood' | 'journal'
const activeTab = ref<Tab>('mood')

// ============================
// MOOD TRACKING
// ============================

interface MoodEntry {
  id: number
  user_id: string
  emoji: string
  label: string
  note: string | null
  created_at: string
}

interface MoodHistoryResponse {
  entries: MoodEntry[]
  total: number
  days: number
}

interface MoodStreakResponse {
  streak_days: number
  total_logs: number
}

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

const selectedEmoji = ref<string | null>(null)
const moodNote = ref('')
const moodSubmitting = ref(false)
const moodError = ref<string | null>(null)
const cooldown = ref<string | null>(null)
const moodSuccess = ref<string | null>(null)

const moodEntries = ref<MoodEntry[]>([])
const streak = ref<MoodStreakResponse | null>(null)
const loadingMoodHistory = ref(true)

const selectedLabel = computed(() => {
  if (!selectedEmoji.value) return null
  return moods.find(m => m.emoji === selectedEmoji.value)?.label ?? null
})

const moodNoteLength = computed(() => moodNote.value.length)

const groupedMoodEntries = computed(() => {
  const groups: { label: string; entries: MoodEntry[] }[] = []
  const today = new Date().toDateString()
  const yesterday = new Date(Date.now() - 86400000).toDateString()

  for (const entry of moodEntries.value) {
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

function selectMood(emoji: string) {
  selectedEmoji.value = emoji
  moodError.value = null
  cooldown.value = null
}

async function logMood() {
  if (!selectedEmoji.value || moodSubmitting.value) return

  moodSubmitting.value = true
  moodError.value = null
  cooldown.value = null

  try {
    await api.post('/api/life/mood', {
      emoji: selectedEmoji.value,
      note: moodNote.value.trim() || null,
    })
    selectedEmoji.value = null
    moodNote.value = ''
    moodSuccess.value = 'Mood logged successfully!'
    setTimeout(() => { moodSuccess.value = null }, 2000)
    await Promise.all([fetchMoodHistory(), fetchStreak()])
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      const body = e.body as Record<string, string>
      const detail = body.detail ?? ''
      const isoMatch = detail.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
      if (isoMatch) {
        const diff = new Date(isoMatch[0]).getTime() - Date.now()
        const hrs = Math.ceil(diff / 3600000)
        cooldown.value = hrs > 1 ? `Next mood log available in ~${hrs} hours.` : 'Next mood log available in less than an hour.'
      } else {
        cooldown.value = detail || 'Rate limit reached. Try again later.'
      }
    } else if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      moodError.value = body.detail ?? `Error (${e.status})`
    } else {
      moodError.value = 'Network error — is the backend running?'
    }
  } finally {
    moodSubmitting.value = false
  }
}

async function fetchMoodHistory() {
  try {
    const res = await api.get<MoodHistoryResponse>('/api/life/mood?days=30')
    moodEntries.value = res.entries
  } catch {
    // Silent
  }
}

async function fetchStreak() {
  try {
    streak.value = await api.get<MoodStreakResponse>('/api/life/mood/streak')
  } catch {
    // Silent
  }
}

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
  await Promise.all([fetchMoodHistory(), fetchStreak(), fetchJournalEntries()])
  loadingMoodHistory.value = false
  loadingJournal.value = false
})
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-10 animate-fade-in">

    <!-- Success Toasts -->
    <transition name="fade">
      <div
        v-if="moodSuccess || journalSuccess"
        class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-6 py-3 rounded-lg bg-emerald-600 text-white font-medium text-sm shadow-lg"
      >
        {{ moodSuccess || journalSuccess }}
      </div>
    </transition>

    <!-- Header + Streak -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-txt-primary">ZugaLife</h1>
        <p class="text-sm text-txt-secondary mt-1">Track, reflect, understand.</p>
      </div>
      <div
        v-if="streak && streak.streak_days > 0"
        class="glass-card px-4 py-2 flex items-center gap-2"
      >
        <span class="text-lg">🔥</span>
        <div>
          <p class="text-sm font-semibold text-txt-primary">{{ streak.streak_days }}-day streak</p>
          <p class="text-xs text-txt-muted">{{ streak.total_logs }} total logs</p>
        </div>
      </div>
      <div
        v-else-if="streak"
        class="glass-card px-4 py-2 flex items-center gap-2"
      >
        <span class="text-lg">📊</span>
        <p class="text-sm text-txt-muted">{{ streak.total_logs }} total logs</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-6 border-b border-bdr">
      <button
        @click="activeTab = 'mood'"
        class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
        :class="activeTab === 'mood'
          ? 'text-accent border-accent'
          : 'text-txt-muted border-transparent hover:text-txt-primary'"
      >
        Mood
      </button>
      <button
        @click="activeTab = 'journal'"
        class="px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px"
        :class="activeTab === 'journal'
          ? 'text-accent border-accent'
          : 'text-txt-muted border-transparent hover:text-txt-primary'"
      >
        Journal
      </button>
    </div>

    <!-- ===== MOOD TAB ===== -->
    <template v-if="activeTab === 'mood'">
      <div class="glass-card p-6 mb-6">
        <div class="grid grid-cols-4 gap-3 mb-4">
          <button
            v-for="mood in moods"
            :key="mood.emoji"
            @click="selectMood(mood.emoji)"
            class="flex flex-col items-center gap-1.5 py-3 rounded-xl transition-all duration-200"
            :class="selectedEmoji === mood.emoji
              ? 'bg-accent/15 ring-1 ring-accent/50 scale-105'
              : 'hover:bg-surface-3 hover:scale-105'"
          >
            <span class="text-3xl">{{ mood.emoji }}</span>
            <span
              class="text-[13px] font-medium transition-colors"
              :class="selectedEmoji === mood.emoji ? 'text-accent' : 'text-txt-muted'"
            >
              {{ mood.label }}
            </span>
          </button>
        </div>

        <div class="mt-4" :class="selectedLabel ? 'border-t border-bdr pt-4' : ''">
          <div v-if="selectedLabel" class="flex items-center gap-2 mb-2 animate-fade-in">
            <span class="text-lg">{{ selectedEmoji }}</span>
            <span class="text-sm text-txt-primary font-medium">{{ selectedLabel }}</span>
          </div>
          <textarea
            v-model="moodNote"
            placeholder="Add a note (optional)"
            maxlength="500"
            rows="2"
            class="input-field resize-none text-sm"
          />
          <p
            v-if="moodNoteLength > 0"
            class="text-right text-xs mt-1"
            :class="moodNoteLength > 450 ? 'text-amber-400' : 'text-txt-muted'"
          >
            {{ moodNoteLength }}/500
          </p>
        </div>

        <p v-if="moodError" class="text-sm text-red-400 mt-3">{{ moodError }}</p>
        <p v-if="cooldown" class="text-sm text-amber-400 mt-3">{{ cooldown }}</p>

        <button
          @click="logMood"
          :disabled="!selectedEmoji || moodSubmitting"
          class="btn-primary w-full mt-4"
        >
          <span v-if="moodSubmitting" class="inline-flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Logging...
          </span>
          <span v-else>Log Mood</span>
        </button>
      </div>

      <div>
        <h2 class="text-lg font-semibold text-txt-primary mb-4">Recent Moods</h2>
        <div v-if="loadingMoodHistory" class="text-sm text-txt-muted">Loading...</div>
        <div v-else-if="moodEntries.length === 0" class="glass-card p-6 text-center">
          <p class="text-txt-muted">How are you feeling?</p>
        </div>
        <div v-else class="space-y-5">
          <div v-for="group in groupedMoodEntries" :key="group.label">
            <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-2">{{ group.label }}</p>
            <div class="space-y-2">
              <div
                v-for="entry in group.entries"
                :key="entry.id"
                class="glass-card px-4 py-3 flex items-start gap-3 animate-slide-up"
              >
                <span class="text-2xl flex-shrink-0">{{ entry.emoji }}</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-txt-primary">{{ entry.label }}</span>
                    <span class="text-xs text-txt-muted">{{ timeAgo(entry.created_at) }}</span>
                  </div>
                  <p v-if="entry.note" class="text-sm text-txt-secondary mt-0.5 break-words">{{ entry.note }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
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
            <p class="text-xs text-txt-muted mb-2">Mood tag (optional)</p>
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
