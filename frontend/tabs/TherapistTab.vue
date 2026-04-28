<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { api, ApiError } from '@core/api/client'
import { useLifeShared } from '../composables/useLifeShared'
import { moodIcons } from '../icons'
import {
  AlertTriangle,
  Lightbulb,
  Loader2,
  MessageCircleHeart,
  ScrollText,
  Send,
  Trash2,
  Pencil,
} from 'lucide-vue-next'
import WellnessAvatar from '../components/WellnessAvatar.vue'
import { useAvatarSpeech } from '../composables/useAvatarSpeech'

// ── Shared composable ──────────────────────────────────────────
const {
  moods,
  withCelebration,
  handleInsufficientTokens,
  handleServiceError,
  notifyTokenSpend,
  celebration,
  renderMarkdown,
  formatDate,
  tokenLabel,
} = useLifeShared()

// ── Emits ─────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'session-active', value: boolean): void
  (e: 'success'): void
}>()

// ── Types ─────────────────────────────────────────────────────
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

// ── State ─────────────────────────────────────────────────────
const therapistView = ref<TherapistView>('chat')

const therapistMessages = ref<TherapistMessage[]>([])
const therapistInput = ref('')
const therapistSending = ref(false)
const therapistGreeting = ref('')
const therapistDisclaimer = "I'm an AI wellness companion, not a licensed therapist or counselor. I draw from psychology, philosophy, and contemplative traditions to help you reflect. I make mistakes \u2014 please push back when something doesn't feel right."
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
// Spinner states for the Notes view: `loadingNotes` while the list fetch is
// in flight, `notesGenerating` while a just-ended session is saving server-
// side. The latter renders a "Generating your notes..." card at the top of
// the list, so a user who pops over to Notes immediately after pressing
// "Save & End Session" sees something is happening instead of a stale list.
const loadingNotes = ref(false)
const notesGenerating = ref(false)
const therapistEditThemes = ref('')
const therapistEditPatterns = ref('')
const therapistEditFollowUp = ref('')

const therapistMessagesRemaining = ref(20)
const therapistMoodBefore = ref<string | null>(null)
const therapistMoodAfter = ref<string | null>(null)
const therapistRating = ref<number | null>(null)
const therapistShowEndMood = ref(false)

// ── Tips on how to write to the wellness companion ──────────────
// Static pool — rotates each session, user can cycle manually.
const THERAPIST_TIPS = [
  'Start with one specific situation from today, not a general feeling.',
  'Be honest about the messy parts — vague input gets vague guidance.',
  'Name the emotion if you can. "Frustrated" lands different from "fine."',
  'Write like no one is listening, then send what is true.',
  'Not sure where to start? Describe the last thing that bothered you.',
  'Specifics help more than summaries — the time, the place, what was said.',
  'Push back when something does not fit. This is not a quiz.',
  'Notice what your body is doing. Tight shoulders? Holding breath?',
  'If a thought keeps looping, write the loop out — it loses power on the page.',
  'You can ask for a reframe, a question back, or just to be heard. Say which.',
  'Bring the smallest version of the problem first. You can zoom out later.',
  'Try writing in second person if first person feels too close.',
  'If you are avoiding a topic, that is usually the one worth opening.',
  'No warm-up needed — start in the middle.',
  'Describe the situation as if to a friend who was not there.',
  'If you keep saying "I should..." — what would happen if you did not?',
  'Distinguish what happened from what it meant to you.',
  'Ask what you are hoping to get out of this session before you start.',
  'Where you are emotionally matters — morning lands different from late-night.',
  'It is okay to not know what is wrong. Start with "something feels off."',
]
const currentTip = ref(THERAPIST_TIPS[Math.floor(Math.random() * THERAPIST_TIPS.length)])
function cycleTip() {
  // Pick a different tip than the current one
  let next = currentTip.value
  while (next === currentTip.value && THERAPIST_TIPS.length > 1) {
    next = THERAPIST_TIPS[Math.floor(Math.random() * THERAPIST_TIPS.length)]
  }
  currentTip.value = next
}


const chatContainer = ref<HTMLElement | null>(null)

// ── Avatar + speech ───────────────────────────────────────────
const avatarRef = ref<InstanceType<typeof WellnessAvatar> | null>(null)
const avatarEnabled = ref(localStorage.getItem('zugalife_avatar_enabled') !== '0')
const voiceEnabled = ref(localStorage.getItem('zugalife_voice_enabled') !== '0')

const { speak: avatarSpeak, stop: avatarStop, speaking: avatarSpeaking } = useAvatarSpeech((v) => {
  ;(avatarRef.value as any)?.setMouthOpen(v)
})

function toggleVoice() {
  voiceEnabled.value = !voiceEnabled.value
  localStorage.setItem('zugalife_voice_enabled', voiceEnabled.value ? '1' : '0')
  if (!voiceEnabled.value) avatarStop()
}

// ── Greeting cache ─────────────────────────────────────────────
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

// ── Watchers ──────────────────────────────────────────────────
watch(therapistMessages, () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}, { deep: true })

watch(therapistSessionActive, (val) => {
  emit('session-active', val)
})

// ── API functions ─────────────────────────────────────────────
async function fetchTherapistStatus() {
  try {
    therapistStatus.value = await api.get<TherapistStatus>('/api/life/therapist/status')
    therapistAvailable.value = true
  } catch {
    therapistAvailable.value = false
  }
}

async function fetchTherapistGreeting() {
  try {
    const res = await api.get<{ greeting: string; is_first_session: boolean; disclaimer: string }>('/api/life/therapist/greeting')
    therapistGreeting.value = res.greeting
    cacheGreeting(res.greeting)
  } catch (e) {
    if (e instanceof ApiError && e.status === 402) {
      therapistError.value = handleInsufficientTokens('Wellness Bot')
    } else if (e instanceof ApiError && e.status >= 500) {
      therapistError.value = handleServiceError('Wellness Bot Unavailable', 'The AI service is temporarily down. Please try again in a few minutes.')
    }
    therapistGreeting.value = ''
  }
}

async function fetchTherapistNotes() {
  loadingNotes.value = true
  try {
    const res = await api.get<{ notes: TherapistSessionNote[]; total: number }>('/api/life/therapist/notes')
    therapistNotes.value = res.notes
  } catch { /* silent */ } finally {
    loadingNotes.value = false
  }
}

async function startTherapistSession() {
  therapistMessages.value = []
  therapistSessionActive.value = true
  therapistError.value = null
  therapistMessagesRemaining.value = 20
  therapistMoodBefore.value = null
  therapistMoodAfter.value = null
  therapistRating.value = null
  therapistShowEndMood.value = false
  therapistSending.value = true

  // Pick a fresh tip for this session
  cycleTip()

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
    if (voiceEnabled.value && avatarEnabled.value) {
      avatarSpeak(res.content).catch(() => { /* silent — chat still works */ })
    }
    therapistMessagesRemaining.value = res.session_messages_remaining
    notifyTokenSpend()

    // Auto-end session when limit reached (therapist already wrapped up naturally)
    if (res.session_messages_remaining <= 0) {
      therapistSending.value = false
      await endTherapistSession()
      return
    }
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 402) {
        therapistError.value = handleInsufficientTokens('Wellness Bot')
      } else if (e.status === 429) {
        therapistError.value = handleServiceError('Session Limit Reached', detail ?? 'You\'ve reached the session limit for today. Come back tomorrow!')
      } else if (e.status === 503 || e.status >= 500) {
        therapistError.value = handleServiceError('Wellness Bot Unavailable', 'The AI service is temporarily down. Your tokens were not charged. Please try again in a few minutes.')
        therapistAvailable.value = false
      } else {
        therapistError.value = handleServiceError('Error', detail ?? 'Something went wrong. Please try again.')
      }
    } else {
      therapistError.value = handleServiceError('Connection Issue', 'We couldn\'t reach the server. Check your internet connection and try again.')
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

  // Show mood-after + rating capture before ending
  if (!therapistShowEndMood.value) {
    therapistShowEndMood.value = true
    return  // Wait for user to capture mood/rating, then call again
  }

  // Capture messages before clearing UI — user doesn't wait for the save
  const apiMessages = therapistMessages.value.map(m => ({ role: m.role, content: m.content }))
  avatarStop()
  therapistSessionActive.value = false
  therapistMessages.value = []
  therapistEndingSession.value = false
  therapistShowEndMood.value = false
  clearCachedGreeting()
  therapistView.value = 'chat'

  // Domain-milestone modal — mirrors the mood-tracking confirmation pattern
  // (sets celebration.activeBadge, rendered by CelebrationOverlay). Notes
  // generation is async server-side, so the description nudges the user
  // toward Session Notes rather than implying immediate availability.
  notesGenerating.value = true
  celebration.activeBadge.value = {
    badge_key: 'therapy_session_saved',
    title: 'Session Saved',
    description: 'Your notes are being generated — check Session Notes in a moment.',
  }

  // Save in background with mood and rating
  withCelebration(() =>
    api.post<TherapistSessionNote>('/api/life/therapist/end-session', {
      messages: apiMessages,
      mood_before: therapistMoodBefore.value,
      mood_after: therapistMoodAfter.value,
      rating: therapistRating.value,
    }), 'therapist_session'
  ).then(async (savedNote) => {
    await fetchTherapistStatus()
    await fetchTherapistNotes()
    therapistCurrentNote.value = savedNote
    emit('success')
  }).catch(() => {
    celebration.pushToast({ type: 'info', message: 'Failed to save session notes', duration: 4000 })
  }).finally(() => {
    notesGenerating.value = false
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

// ── Lifecycle ─────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([
    fetchTherapistStatus(),
    fetchTherapistNotes(),
  ])
  loadingTherapist.value = false
})

// ── Expose for parent guard ───────────────────────────────────
defineExpose({ therapistSessionActive, therapistMessages })
</script>

<template>
  <!-- Unavailable state -->
  <div v-if="!therapistAvailable" class="glass-card p-8 text-center">
    <AlertTriangle :size="32" class="mx-auto mb-3 text-accent" />
    <h3 class="text-lg font-semibold text-txt-primary mb-2">Wellness Bot Unavailable</h3>
    <p class="text-sm text-txt-muted">The Wellness Bot is currently unreachable. Please try again later.</p>
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
        class="px-4 py-2.5 text-xs font-medium rounded-lg transition-colors"
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
        <div v-if="therapistDisclaimer" class="glass-card p-4 border border-accent/20">
          <div class="flex items-start gap-2">
            <AlertTriangle :size="16" class="text-accent mt-0.5 shrink-0" />
            <p class="text-xs text-txt-muted leading-relaxed">{{ therapistDisclaimer }}</p>
          </div>
        </div>

        <div class="glass-card p-8 text-center">
          <MessageCircleHeart :size="40" class="mx-auto mb-4 text-accent" />
          <h3 class="text-lg font-semibold text-txt-primary mb-2">Ready to talk?</h3>
          <p class="text-sm text-txt-muted mb-4 max-w-md mx-auto">
            A private space to reflect, process, and explore what's on your mind.
            Powered by Venice AI — your data stays private.
          </p>
          <!-- Mood before session -->
          <div class="mb-4">
            <p class="text-xs text-txt-muted mb-2">How are you feeling right now?</p>
            <div class="flex flex-wrap justify-center gap-1.5">
              <button
                v-for="mood in moods.slice(0, 6)"
                :key="mood.emoji"
                @click="therapistMoodBefore = therapistMoodBefore === mood.emoji ? null : mood.emoji"
                class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
                :class="therapistMoodBefore === mood.emoji ? 'bg-accent/15 ring-1 ring-accent/50' : 'text-txt-muted hover:bg-surface-3'"
              >
                <component :is="moodIcons[mood.emoji]" :size="18" v-if="moodIcons[mood.emoji]" />
              </button>
            </div>
          </div>
          <button
            @click="startTherapistSession()"
            :disabled="therapistStatus?.sessions_remaining === 0"
            class="px-6 py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {{ therapistStatus?.sessions_remaining === 0 ? 'No sessions left today' : 'Start Session' }}
          </button>
        </div>
      </div>

      <!-- Active session: chat. Fit to visible viewport so the input is
           anchored at the bottom and only the messages area scrolls.
           - 100dvh (dynamic) tracks mobile URL bar + soft keyboard so the
             input doesn't fall below the fold on iOS Safari.
           - 220px ≈ TopNav + page top padding + back-nav row + bottom
             padding (rough but stable enough for both mobile and desktop). -->
      <div v-else class="flex flex-col h-[calc(100dvh-220px)] min-h-[320px] max-h-[calc(100dvh-220px)]">
        <!-- Avatar -->
        <div v-if="avatarEnabled" class="mb-3 rounded-xl overflow-hidden bg-surface-2/40 border border-bdr/40">
          <WellnessAvatar ref="avatarRef" :height="280" />
          <div class="flex items-center justify-between px-3 py-1.5 text-xs text-txt-muted border-t border-bdr/40">
            <span>{{ avatarSpeaking ? 'Speaking…' : 'Listening' }}</span>
            <button
              @click="toggleVoice()"
              class="px-2 py-0.5 rounded hover:bg-surface-3 transition-colors"
              :title="voiceEnabled ? 'Mute voice' : 'Unmute voice'"
            >
              {{ voiceEnabled ? 'Mute' : 'Unmute' }}
            </button>
          </div>
        </div>
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

        <!-- Writing tip (shown before user replies) -->
        <div v-if="therapistMessages.length <= 1" class="mb-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-surface-2/40 border border-bdr/40">
          <Lightbulb :size="14" class="text-accent/70 flex-shrink-0 mt-0.5" />
          <p class="flex-1 text-xs text-txt-secondary italic leading-relaxed">{{ currentTip }}</p>
          <button
            @click="cycleTip()"
            class="flex-shrink-0 p-1 rounded text-txt-muted/60 hover:text-txt-secondary hover:bg-surface-3 transition-colors"
            title="Show a different tip"
            aria-label="Show a different tip"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
          </button>
        </div>

        <!-- End-session mood + rating capture -->
        <div v-if="therapistShowEndMood" class="border-t border-bdr pt-4 mb-3 space-y-4 animate-fade-in">
          <div>
            <p class="text-xs text-txt-muted mb-2">How are you feeling now?</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="mood in moods.slice(0, 6)"
                :key="mood.emoji"
                @click="therapistMoodAfter = therapistMoodAfter === mood.emoji ? null : mood.emoji"
                class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
                :class="therapistMoodAfter === mood.emoji ? 'bg-accent/15 ring-1 ring-accent/50' : 'text-txt-muted hover:bg-surface-3'"
              >
                <component :is="moodIcons[mood.emoji]" :size="18" v-if="moodIcons[mood.emoji]" />
              </button>
            </div>
          </div>
          <div>
            <p class="text-xs text-txt-muted mb-2">How helpful was this session?</p>
            <div class="flex gap-1">
              <button
                v-for="star in [1, 2, 3, 4, 5]"
                :key="star"
                @click="therapistRating = therapistRating === star ? null : star"
                class="text-lg transition-colors"
                :class="therapistRating && star <= therapistRating ? 'text-accent' : 'text-surface-3 hover:text-accent/50'"
              >
                &#9733;
              </button>
            </div>
          </div>
          <button
            @click="endTherapistSession()"
            class="btn-primary w-full text-sm"
          >
            Save & End Session
          </button>
        </div>

        <!-- Input area -->
        <div v-if="!therapistShowEndMood" class="border-t border-bdr pt-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs text-txt-muted">{{ therapistMessagesRemaining }} messages left</span>
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
      <!-- Loading: list fetch in flight (first visit / refresh) -->
      <div v-if="loadingNotes && therapistNotes.length === 0 && !notesGenerating" class="glass-card p-8 text-center">
        <Loader2 :size="22" class="mx-auto mb-2 text-accent animate-spin" />
        <p class="text-sm text-txt-muted">Loading your session notes…</p>
      </div>

      <div v-else-if="therapistNotes.length === 0 && !notesGenerating" class="glass-card p-8 text-center">
        <ScrollText :size="32" class="mx-auto mb-3 text-txt-muted" />
        <p class="text-sm text-txt-muted">No session notes yet. Complete a session to see notes here.</p>
      </div>

      <div v-else class="space-y-3">
        <!-- Generating: a session was just ended, end-session POST is in flight.
             Sits at the top of the list; replaced by the real note row when the
             save resolves and fetchTherapistNotes returns. -->
        <div v-if="notesGenerating" class="glass-card p-4 flex items-center gap-3 border border-accent/30 animate-fade-in">
          <Loader2 :size="20" class="text-accent animate-spin flex-shrink-0" />
          <div>
            <p class="text-sm font-medium text-txt-primary">Generating your session notes…</p>
            <p class="text-xs text-txt-muted mt-0.5">This usually takes a few seconds.</p>
          </div>
        </div>
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
              class="p-2 rounded-lg text-txt-muted/40 hover:text-red-400 hover:bg-red-400/10 transition-all"
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
            <span>{{ tokenLabel(note.cost) }}</span>
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
          <span>{{ tokenLabel(therapistCurrentNote.cost) }}</span>
        </div>
      </div>
    </template>
  </template>
</template>
