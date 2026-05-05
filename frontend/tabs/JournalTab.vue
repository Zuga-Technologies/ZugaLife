<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { api, ApiError, getToken } from '@core/api/client'
import { ArrowLeft, ArrowRight, BookOpen, Bold, ChevronRight, Download, Heading2, Italic, List, Meh, Sparkles, Trash2 } from 'lucide-vue-next'
import { moodIcons } from '../icons'
import { useLifeShared } from '../composables/useLifeShared'

const emit = defineEmits<{
  (e: 'success', message: string): void
}>()

const {
  moods,
  withCelebration,
  notifyTokenSpend,
  handleInsufficientTokens,
  handleServiceError,
  parseUTC,
  timeAgo,
  formatDate,
  renderMarkdown,
  tokenLabel,
} = useLifeShared()

// ── Types ─────────────────────────────────────────────────────

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
  tags: string[]
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
  tags: string[]
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

// ── State ─────────────────────────────────────────────────────

type JournalViewState = 'list' | 'compose' | 'detail'
const journalView = ref<JournalViewState>('list')

const journalEntries = ref<JournalEntryBrief[]>([])
const totalJournalEntries = ref(0)
const loadingJournal = ref(true)

const composeTitle = ref('')
const composeContent = ref('')
const showJournalPrompts = ref(false)
const dailyJournalPrompt = ref<{ title: string; prompt: string; category: string } | null>(null)
const composeMood = ref<string | null>(null)
const composeTags = ref<string[]>([])
const journalSubmitting = ref(false)

const JOURNAL_TAGS = ['Work', 'Social', 'Exercise', 'Family', 'Creative', 'Rest', 'Travel', 'Health', 'Learning', 'Relationship']

const JOURNAL_PROMPTS = [
  'What challenged you today, and how did you handle it?',
  'What are you grateful for right now?',
  'What did you learn today that surprised you?',
  'What\'s been on your mind that you haven\'t said out loud?',
  'Describe a moment today that made you feel something.',
  'What would you do differently if you could redo today?',
  'What\'s one thing you\'re avoiding, and why?',
  'Write about someone who impacted your day.',
  'What does your ideal tomorrow look like?',
  'What pattern have you noticed in yourself lately?',
]

// Rotate prompts by day so user sees different ones
const todayPrompts = computed(() => {
  const dayIndex = Math.floor(Date.now() / 86400000)
  const shuffled = [...JOURNAL_PROMPTS].sort((a, b) => {
    const ha = (dayIndex * 2654435761 + a.length) % 1000
    const hb = (dayIndex * 2654435761 + b.length) % 1000
    return ha - hb
  })
  return shuffled.slice(0, 3)
})

const currentEntry = ref<JournalEntryFull | null>(null)
const loadingDetail = ref(false)
const reflecting = ref(false)
const reflectionsRemaining = ref(3)

const journalError = ref<string | null>(null)
const journalSuccess = ref<string | null>(null)

const contentLength = computed(() => composeContent.value.length)
// Single trim per keystroke. Was 3 separate `composeContent.trim()` calls
// in the template — each O(n) on the full string — which made typing
// laggy in long entries.
const composeIsBlank = computed(() => composeContent.value.trim().length === 0)

// "Next entry" — index of the entry chronologically AFTER the current one
// in the displayed list (newest-first, so 'next' = older). null if there's
// no next entry.
const nextEntryId = computed<number | null>(() => {
  if (!currentEntry.value) return null
  const idx = journalEntries.value.findIndex(e => e.id === currentEntry.value!.id)
  if (idx < 0 || idx >= journalEntries.value.length - 1) return null
  return journalEntries.value[idx + 1].id
})

const composeMoodLabel = computed(() => {
  if (!composeMood.value) return null
  return moods.value.find(m => m.emoji === composeMood.value)?.label ?? null
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

// Export menus
const showExportMenu = ref(false)
const showBulkExportMenu = ref(false)

// Two-step delete — bible §11 button.danger MUST NOT fire destructive
// action immediately. First click flips to "Click to confirm" for 4s.
const confirmingDelete = ref(false)
let confirmDeleteTimer: ReturnType<typeof setTimeout> | null = null

// ── Functions ─────────────────────────────────────────────────

function usePrompt(prompt: string) {
  composeContent.value = `**${prompt}**\n\n`
}

function toggleComposeTag(tag: string) {
  const idx = composeTags.value.indexOf(tag)
  if (idx >= 0) composeTags.value.splice(idx, 1)
  else composeTags.value.push(tag)
}

/** Wire Ctrl+B / Cmd+B → bold and Ctrl+I / Cmd+I → italic on the journal
 *  textarea. Heading + list don't get shortcuts (Ctrl+H is browser history,
 *  Ctrl+L is address bar). The toolbar still works for those. */
function handleTextareaKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return
  const k = e.key.toLowerCase()
  if (k === 'b') {
    e.preventDefault()
    insertFormat('bold')
  } else if (k === 'i') {
    e.preventDefault()
    insertFormat('italic')
  }
}

function insertFormat(type: 'bold' | 'italic' | 'heading' | 'list') {
  const textarea = document.querySelector<HTMLTextAreaElement>('.journal-textarea')
  if (!textarea) return
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const text = composeContent.value
  const selected = text.substring(start, end)

  let replacement: string
  let cursorOffset: number

  switch (type) {
    case 'bold':
      replacement = selected ? `**${selected}**` : '**bold text**'
      cursorOffset = selected ? replacement.length : 2
      break
    case 'italic':
      replacement = selected ? `*${selected}*` : '*italic text*'
      cursorOffset = selected ? replacement.length : 1
      break
    case 'heading':
      replacement = selected ? `## ${selected}` : '## Heading'
      cursorOffset = replacement.length
      break
    case 'list':
      replacement = selected
        ? selected.split('\n').map(l => `- ${l}`).join('\n')
        : '- Item'
      cursorOffset = replacement.length
      break
  }

  composeContent.value = text.substring(0, start) + replacement + text.substring(end)
  nextTick(() => {
    textarea.focus()
    const pos = start + cursorOffset
    textarea.setSelectionRange(pos, pos)
  })
}

function goToCompose() {
  composeTitle.value = ''
  composeContent.value = ''
  composeMood.value = null
  composeTags.value = []
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

async function fetchDailyJournalPrompt() {
  try {
    dailyJournalPrompt.value = await api.get<{ title: string; prompt: string; category: string }>('/api/life/journal/prompt')
  } catch { /* silent */ }
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
        tags: composeTags.value.length ? composeTags.value : null,
      }), 'journal_entry'
    )
    journalSuccess.value = 'Journal entry saved!'
    emit('success', 'Journal entry saved!')
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
    notifyTokenSpend()
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      if (e.status === 402) {
        journalError.value = handleInsufficientTokens('Journal Reflections')
      } else if (e.status === 429) {
        journalError.value = handleServiceError('Reflection Limit', body.detail ?? 'Maximum reflections reached for this entry.')
      } else if (e.status >= 500) {
        journalError.value = handleServiceError('Service Unavailable', 'The AI service is temporarily down. Your tokens were not charged. Please try again in a few minutes.')
      } else {
        journalError.value = handleServiceError('Error', body.detail ?? 'Something went wrong. Please try again.')
      }
    } else {
      journalError.value = handleServiceError('Connection Issue', 'We couldn\'t reach the server. Check your internet connection and try again.')
    }
  } finally {
    reflecting.value = false
  }
}

async function deleteEntry() {
  if (!currentEntry.value) return
  // First click — arm confirmation for 4 seconds
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    if (confirmDeleteTimer) clearTimeout(confirmDeleteTimer)
    confirmDeleteTimer = setTimeout(() => { confirmingDelete.value = false }, 4000)
    return
  }
  // Second click — actually delete
  if (confirmDeleteTimer) clearTimeout(confirmDeleteTimer)
  confirmingDelete.value = false
  journalError.value = null
  try {
    await api.delete(`/api/life/journal/${currentEntry.value.id}`)
    journalSuccess.value = 'Entry deleted.'
    emit('success', 'Entry deleted.')
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

async function exportAllJournal(format: 'markdown' | 'json') {
  showBulkExportMenu.value = false
  try {
    const resp = await fetch(`/api/life/journal/export?format=${format}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (!resp.ok) throw new Error(`Export failed (${resp.status})`)
    const blob = await resp.blob()
    const disposition = resp.headers.get('Content-Disposition') ?? ''
    const match = disposition.match(/filename=(.+)/)
    const ext = format === 'json' ? 'json' : 'zip'
    const filename = match ? match[1] : `zugalife-journal.${ext}`
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

// ── Lifecycle ─────────────────────────────────────────────────

onMounted(async () => {
  loadingJournal.value = true
  await Promise.all([
    fetchJournalEntries(),
    fetchDailyJournalPrompt(),
  ])
  loadingJournal.value = false
})
</script>

<template>
  <!-- ===== JOURNAL TAB ===== -->
  <!-- list + detail share the same chrome (header + Export All + New Entry).
       Only compose mode swaps to a dedicated authoring view. -->
  <template v-if="journalView !== 'compose'">
    <div class="flex items-center justify-between mb-6">
      <p class="text-sm text-txt-secondary">Write, reflect, understand.</p>
      <div class="flex items-center gap-2">
        <div class="relative">
          <button @click="showBulkExportMenu = !showBulkExportMenu" class="text-xs text-txt-muted hover:text-accent transition-colors px-2 py-2 flex items-center gap-1">
            <Download :size="12" />
            Export All
          </button>
          <div v-if="showBulkExportMenu" class="absolute right-0 top-full mt-1 glass-card p-1 rounded-lg shadow-lg z-20 min-w-[170px] max-w-[calc(100vw-2rem)]">
            <button @click="exportAllJournal('markdown')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-surface-3 px-3 py-2 rounded transition-colors">
              Markdown (.zip)
            </button>
            <button @click="exportAllJournal('json')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-surface-3 px-3 py-2 rounded transition-colors">
              JSON (.json)
            </button>
          </div>
        </div>
        <button @click="goToCompose" class="btn-primary px-5 py-2 text-sm">New Entry</button>
      </div>
    </div>
  </template>

  <!-- ===== LIST ===== -->
  <template v-if="journalView === 'list'">
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
            <component :is="moodIcons[entry.mood_emoji]" v-if="entry.mood_emoji && moodIcons[entry.mood_emoji]" :size="22" class="text-accent/60 flex-shrink-0" />
            <Meh v-else-if="entry.mood_emoji" :size="22" class="text-accent/60 flex-shrink-0" />
            <BookOpen v-else :size="22" class="text-txt-muted flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-txt-primary truncate">{{ entry.title || entry.content_preview.slice(0, 60) }}</span>
                <span class="text-xs text-txt-muted flex-shrink-0 ml-auto tabular-nums">{{ timeAgo(entry.created_at) }}</span>
              </div>
              <p v-if="entry.title" class="text-sm text-txt-secondary mt-0.5 truncate">{{ entry.content_preview }}</p>
              <div class="flex items-center gap-1.5 mt-1 flex-wrap">
                <span v-for="tag in (entry.tags || [])" :key="tag" class="px-1.5 py-0.5 text-xs rounded-full bg-surface-3 text-txt-muted">{{ tag }}</span>
                <span v-if="entry.reflection_count > 0" class="inline-flex items-center gap-1 text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full">
                  <Sparkles :size="10" />
                  {{ entry.reflection_count }}
                </span>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  </template>

  <template v-if="journalView === 'compose'">
    <div class="mb-6">
      <button @click="goToJournalList" class="inline-flex items-center gap-1.5 text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2" aria-label="Back to journal list">
        <ArrowLeft :size="14" />
        <span>Back</span>
      </button>
      <h2 class="text-xl font-bold text-txt-primary">New Entry</h2>
    </div>

    <!-- Daily guided prompt (psychology-informed, from backend) -->
    <div v-if="composeIsBlank && dailyJournalPrompt" class="mb-5 animate-fade-in">
      <div class="relative p-5 rounded-xl border overflow-hidden transition-colors backdrop-blur-sm"
        :class="{
          'bg-accent-alt/6 border-accent-alt/15': dailyJournalPrompt.category === 'expressive',
          'bg-accent/6 border-accent/15': dailyJournalPrompt.category === 'gratitude',
          'bg-info/6 border-info/15': dailyJournalPrompt.category === 'reflection',
        }"
      >
        <!-- Side accent -->
        <div class="absolute top-0 left-0 bottom-0 w-[3px]"
          :class="{
            'bg-gradient-to-b from-accent-alt to-accent-alt-dim': dailyJournalPrompt.category === 'expressive',
            'bg-gradient-to-b from-accent-bright to-accent-dim': dailyJournalPrompt.category === 'gratitude',
            'bg-gradient-to-b from-info to-info': dailyJournalPrompt.category === 'reflection',
          }"
        />
        <div class="pl-3">
          <p class="text-[10px] font-bold uppercase tracking-widest mb-2 opacity-70"
            :class="{
              'text-accent-alt': dailyJournalPrompt.category === 'expressive',
              'text-accent': dailyJournalPrompt.category === 'gratitude',
              'text-info': dailyJournalPrompt.category === 'reflection',
            }"
          >Today's prompt &mdash; {{ dailyJournalPrompt.category }}</p>
          <p class="text-base text-txt-primary font-medium mb-4 leading-relaxed">{{ dailyJournalPrompt.prompt }}</p>
          <div class="flex items-center gap-4">
            <button
              @click="usePrompt(dailyJournalPrompt!.prompt)"
              class="px-4 py-2 text-xs font-semibold rounded-lg transition-all"
              :class="{
                'bg-accent-alt/20 text-accent-alt-bright hover:bg-accent-alt/30': dailyJournalPrompt.category === 'expressive',
                'bg-accent/20 text-accent-bright hover:bg-accent/30': dailyJournalPrompt.category === 'gratitude',
                'bg-info/20 text-info hover:bg-info/30': dailyJournalPrompt.category === 'reflection',
              }"
            >Use this prompt</button>
            <button
              @click="dailyJournalPrompt = null"
              class="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
            >Write freely</button>
          </div>
        </div>
      </div>
    </div>

    <!-- More prompts (shown when daily prompt dismissed or content empty) -->
    <div v-if="composeIsBlank && !dailyJournalPrompt" class="mb-4">
      <button
        @click="showJournalPrompts = !showJournalPrompts"
        class="flex items-center gap-1.5 text-xs text-txt-muted hover:text-txt-secondary uppercase tracking-wider transition-colors mb-2"
        :aria-expanded="showJournalPrompts"
      >
        <ChevronRight :size="12" :class="showJournalPrompts ? 'rotate-90' : ''" class="transition-transform duration-150" />
        Need a starting point?
      </button>
      <div v-if="showJournalPrompts" class="space-y-2 animate-fade-in">
        <button
          v-for="prompt in todayPrompts"
          :key="prompt"
          @click="usePrompt(prompt)"
          class="w-full text-left px-4 py-3 rounded-xl bg-surface-2/50 border border-bdr/50 text-sm text-txt-secondary hover:text-txt-primary hover:border-accent/30 hover:bg-surface-2 transition-all"
        >
          {{ prompt }}
        </button>
      </div>
    </div>

    <div class="glass-card p-6 space-y-4">
      <input v-model="composeTitle" type="text" placeholder="Title (optional)" maxlength="200" class="input-field text-lg font-medium" />

      <!-- Formatting toolbar -->
      <div class="flex items-center gap-1 border-b border-bdr/50 pb-2">
        <button @click="insertFormat('bold')" class="p-2 text-txt-muted hover:text-txt-primary hover:bg-surface-3 rounded transition-colors" title="Bold (Ctrl+B)" aria-label="Bold">
          <Bold :size="14" />
        </button>
        <button @click="insertFormat('italic')" class="p-2 text-txt-muted hover:text-txt-primary hover:bg-surface-3 rounded transition-colors" title="Italic (Ctrl+I)" aria-label="Italic">
          <Italic :size="14" />
        </button>
        <button @click="insertFormat('heading')" class="p-2 text-txt-muted hover:text-txt-primary hover:bg-surface-3 rounded transition-colors" title="Heading" aria-label="Heading">
          <Heading2 :size="14" />
        </button>
        <button @click="insertFormat('list')" class="p-2 text-txt-muted hover:text-txt-primary hover:bg-surface-3 rounded transition-colors" title="List" aria-label="List">
          <List :size="14" />
        </button>
        <span class="flex-1" />
        <span v-if="contentLength > 0" class="text-xs tabular-nums" :class="contentLength > 45000 ? 'text-streak' : 'text-txt-muted'">{{ contentLength.toLocaleString() }}</span>
      </div>

      <textarea
        v-model="composeContent"
        @keydown="handleTextareaKeydown"
        placeholder="What's on your mind?"
        maxlength="50000"
        rows="12"
        class="journal-textarea input-field resize-none text-sm leading-relaxed"
      />

      <!-- Activity tags -->
      <div>
        <p class="text-xs text-txt-muted mb-2">Tag this entry (optional)</p>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="tag in JOURNAL_TAGS"
            :key="tag"
            @click="toggleComposeTag(tag)"
            class="px-2.5 py-1 text-xs rounded-full border transition-all duration-150"
            :class="composeTags.includes(tag)
              ? 'bg-accent/15 border-accent/40 text-accent font-medium'
              : 'border-bdr/50 text-txt-muted hover:border-bdr-hover hover:text-txt-secondary'"
          >
            {{ tag }}
          </button>
        </div>
      </div>

      <!-- Mood picker -->
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

      <p v-if="journalError" class="text-sm text-danger">{{ journalError }}</p>
      <button @click="saveEntry" :disabled="composeIsBlank || journalSubmitting" class="btn-primary w-full">
        <span v-if="journalSubmitting" class="inline-flex items-center gap-2">
          <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          Saving...
        </span>
        <span v-else>Save Entry</span>
      </button>
    </div>
  </template>

  <template v-if="journalView === 'detail'">
    <div v-if="loadingDetail" class="text-sm text-txt-muted">Loading...</div>
    <template v-else-if="currentEntry">
      <div class="glass-card p-6 mb-6">
        <div class="flex items-start justify-between mb-4 gap-4">
          <div class="min-w-0">
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
          <div class="flex items-center gap-2 flex-shrink-0">
            <div class="relative">
              <button @click="showExportMenu = !showExportMenu" class="text-xs text-txt-muted hover:text-accent transition-colors px-3 py-2 flex items-center gap-1">
                <Download :size="12" />
                Export
              </button>
              <div v-if="showExportMenu" class="absolute right-0 top-full mt-1 glass-card p-1 rounded-lg shadow-lg z-20 min-w-[140px] max-w-[calc(100vw-2rem)]">
                <button @click="exportEntry('markdown')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-surface-3 px-3 py-2 rounded transition-colors">
                  Markdown (.md)
                </button>
                <button @click="exportEntry('json')" class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-surface-3 px-3 py-2 rounded transition-colors">
                  JSON (.json)
                </button>
              </div>
            </div>
            <button
              @click="deleteEntry"
              class="text-xs transition-colors px-3 py-2 inline-flex items-center gap-1.5 rounded"
              :class="confirmingDelete
                ? 'text-danger ring-1 ring-danger/50 bg-danger/10 font-medium'
                : 'text-txt-muted hover:text-danger'"
            >
              <Trash2 :size="12" />
              {{ confirmingDelete ? 'Click to confirm' : 'Delete' }}
            </button>
          </div>
        </div>
        <!-- Tags -->
        <div v-if="currentEntry.tags?.length" class="flex flex-wrap gap-1.5 mb-4">
          <span
            v-for="tag in currentEntry.tags"
            :key="tag"
            class="px-2 py-0.5 text-xs rounded-full bg-accent/10 text-accent font-medium"
          >{{ tag }}</span>
        </div>
        <!-- Content rendered with basic markdown -->
        <div class="text-sm text-txt-secondary leading-relaxed journal-content" v-html="renderMarkdown(currentEntry.content)" />
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
              <span class="text-xs text-txt-muted/60" aria-hidden="true">·</span>
              <span class="text-xs text-txt-muted">{{ formatDate(reflection.created_at) }}</span>
              <span class="text-xs text-txt-muted ml-auto">{{ tokenLabel(reflection.cost) }}</span>
            </div>
            <div class="text-sm text-txt-secondary leading-relaxed journal-content" v-html="renderMarkdown(reflection.content)" />
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
      <p v-if="journalError" class="text-sm text-danger mt-3">{{ journalError }}</p>

      <!-- Next entry — keeps the user reading without going back to the list. -->
      <div class="mt-6 flex justify-end">
        <button
          v-if="nextEntryId !== null"
          @click="goToDetail(nextEntryId)"
          class="inline-flex items-center gap-1.5 text-xs text-txt-muted hover:text-accent transition-colors px-3 py-2"
        >
          <span>Next entry</span>
          <ArrowRight :size="13" />
        </button>
        <button
          v-else
          @click="goToJournalList"
          class="text-xs text-txt-muted hover:text-txt-primary transition-colors px-3 py-2"
        >All Entries</button>
      </div>
    </template>
    <div v-else class="glass-card p-6 text-center">
      <p v-if="journalError" class="text-sm text-danger">{{ journalError }}</p>
      <p v-else class="text-sm text-txt-muted">Entry not found.</p>
    </div>
  </template>
</template>
