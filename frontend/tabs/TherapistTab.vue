<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { api, ApiError } from '@core/api/client'
import { useLifeShared } from '../composables/useLifeShared'
import { moodIcons } from '../icons'
import {
  AlertTriangle,
  ArrowLeft,
  Lightbulb,
  Loader2,
  Lock,
  MessageCircleHeart,
  Mic,
  MicOff,
  RotateCw,
  ScrollText,
  Send,
  Star,
  Trash2,
  Pencil,
  User,
  Volume2,
  VolumeX,
  X,
} from 'lucide-vue-next'
import WellnessAvatar from '../components/WellnessAvatar.vue'
import { useAvatarSpeech } from '../composables/useAvatarSpeech'
import { useVoiceLoop } from '../composables/useVoiceLoop'

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

// Companion mood — set from each assistant reply, drives the avatar's visor
// emission color, posture, and idle tempo. Resets to neutral when a new
// session starts so the bot doesn't carry yesterday's mood into today.
type CompanionMood = 'neutral' | 'happy' | 'sad' | 'angry' | 'surprised' | 'relaxed'
const companionMood = ref<CompanionMood>('neutral')
const companionMoodIntensity = ref(0.0)

// Two-step delete for session notes — bible §11 button.danger MUST NOT
// fire destructive action immediately. First click arms confirm for 4s.
const deletingNote = ref<number | null>(null)
let deletingNoteTimer: ReturnType<typeof setTimeout> | null = null

function armDeleteNote(id: number) {
  deletingNote.value = id
  if (deletingNoteTimer) clearTimeout(deletingNoteTimer)
  deletingNoteTimer = setTimeout(() => { deletingNote.value = null }, 4000)
}

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
// Voice is decoupled from avatar visibility: users can keep the avatar on
// screen but mute her, or hide her entirely. Default = on (matches prior
// behaviour where the only way to silence was to hide the avatar).
const avatarVoiceEnabled = ref(localStorage.getItem('zugalife_avatar_voice_enabled') !== '0')
const { speak: avatarSpeak, stop: avatarStop, prewarm: avatarPrewarm, speaking: avatarSpeaking } = useAvatarSpeech((v) => {
  avatarRef.value?.setMouthOpen(v)
})

// Hiding the avatar always stops in-flight speech. Showing the avatar
// re-warms the AudioContext (counts as a user gesture in the same tick).
watch(avatarEnabled, (enabled) => {
  localStorage.setItem('zugalife_avatar_enabled', enabled ? '1' : '0')
  if (!enabled) {
    avatarStop()
  } else if (avatarVoiceEnabled.value) {
    avatarPrewarm().catch(() => { /* best-effort */ })
  }
})

// Mute toggle — independent of avatar visibility. Off = stop any in-flight
// utterance immediately and skip future TTS calls (no Cartesia spend).
watch(avatarVoiceEnabled, (enabled) => {
  localStorage.setItem('zugalife_avatar_voice_enabled', enabled ? '1' : '0')
  if (!enabled) {
    avatarStop()
  } else if (avatarEnabled.value) {
    avatarPrewarm().catch(() => { /* best-effort */ })
  }
})

// Pick up changes from the Settings tab while a chat session is open.
window.addEventListener('storage', (e) => {
  if (e.key === 'zugalife_avatar_enabled') {
    avatarEnabled.value = e.newValue !== '0'
  } else if (e.key === 'zugalife_avatar_voice_enabled') {
    avatarVoiceEnabled.value = e.newValue !== '0'
  }
})

// ── Voice loop (continuous mute/unmute) ───────────────────────
// Pattern lifted from ZugaGamerOverlay's voice service: client-side VAD +
// silence-segmentation. Unmuted = the bot is actively listening; an
// utterance ends on silence and is auto-transcribed and auto-sent. No more
// 2-stage tap-record-tap-stop-tap-send dance.
const voiceInputSupported = !!(typeof window !== 'undefined' && window.MediaRecorder && navigator.mediaDevices?.getUserMedia)
const voiceInputEnabled = ref(localStorage.getItem('zugalife_voice_input_enabled') !== '0')

const {
  muted: voiceMuted,
  phase: voicePhase,
  volume: voiceVolume,
  lastError: voiceLastError,
  interimTranscript: voiceInterim,
  toggle: voiceToggle,
  mute: voiceMute,
} = useVoiceLoop({
  onTranscript: handleVoiceTranscript,
  isOutputSpeaking: () => avatarSpeaking.value,
})

async function handleVoiceTranscript(text: string) {
  if (!text) return
  // Briefly drop the heard text into the input so the user sees what landed,
  // then sendTherapistMessage() reads it back, clears, and ships it.
  const existing = therapistInput.value.trim()
  therapistInput.value = existing ? `${existing} ${text}` : text
  notifyTokenSpend()
  await sendTherapistMessage()
}

// Surface a per-platform hint when the browser has previously denied mic
// access — at that point getUserMedia rejects without re-prompting and the
// user has to flip a setting manually.
async function micPermissionState(): Promise<'granted' | 'denied' | 'prompt' | 'unknown'> {
  try {
    const perms = (navigator as Navigator & { permissions?: { query: (q: { name: PermissionName }) => Promise<PermissionStatus> } }).permissions
    if (!perms) return 'unknown'
    const res = await perms.query({ name: 'microphone' as PermissionName })
    return res.state as 'granted' | 'denied' | 'prompt'
  } catch {
    return 'unknown'
  }
}

function deniedHint(): string {
  const ua = navigator.userAgent.toLowerCase()
  const isMobile = /iphone|ipad|android/.test(ua)
  if (isMobile) {
    if (/iphone|ipad/.test(ua)) {
      return 'Microphone blocked. Open iOS Settings → Safari → Microphone → Allow, then reload this page.'
    }
    return 'Microphone blocked. Open browser site settings (lock icon → permissions) and allow microphone, then reload.'
  }
  return 'Microphone blocked. Click the lock icon in the address bar → Site settings → Microphone → Allow, then reload.'
}

async function toggleVoice() {
  therapistError.value = null

  if (voiceMuted.value) {
    // Mute the avatar so she's not still talking when the user starts to
    // listen for herself. Note: we DON'T early-return on a Permissions API
    // 'denied' state — some browsers report stale denials that getUserMedia
    // would actually re-prompt on. Let getUserMedia be the source of truth.
    avatarStop()
  }

  await voiceToggle()

  if (voiceLastError.value === 'NotAllowedError') {
    therapistError.value = deniedHint()
  } else if (voiceLastError.value === 'unsupported') {
    therapistError.value = 'Voice input not supported on this browser. Type your message instead.'
  } else if (voiceLastError.value && voiceLastError.value !== 'no-credits') {
    // no-credits surfaces via notifyTokenSpend / chat path — no need to double-up.
    therapistError.value = `Mic error: ${voiceLastError.value}. Type your message instead.`
  }
}

// If the user disables voice input from Settings while a session is open,
// kill the loop so the mic releases.
watch(voiceInputEnabled, (v) => {
  if (!v && !voiceMuted.value) voiceMute()
})

window.addEventListener('storage', (e) => {
  if (e.key === 'zugalife_voice_input_enabled') {
    voiceInputEnabled.value = e.newValue !== '0'
    if (e.newValue === '0' && !voiceMuted.value) voiceMute()
  }
})

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
    // An empty cached value is a poison pill — happened to a real user when
    // a previous fetch failed and the empty greeting got cached anyway. Treat
    // empty/whitespace as a miss so we re-fetch.
    if (!cached.greeting || !cached.greeting.trim()) {
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
  // The cross-studio leave-warning forces sessionActive=false directly via
  // the parent's defineExpose handle (skipping endTherapistSession). Without
  // an avatar-stop here, an in-flight TTS fetch resolves AFTER the warning
  // is dismissed and starts playing while the user is on a different tab.
  if (!val) avatarStop()
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
    } else if (e instanceof ApiError && e.status === 429) {
      const detail = (e.body as Record<string, string> | undefined)?.detail
      therapistError.value = handleServiceError('Wellness Bot Busy', detail ?? 'The Wellness Bot is busy right now. Try again in a moment.')
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
  companionMood.value = 'neutral'
  companionMoodIntensity.value = 0.0
  therapistSending.value = true

  // The Start button click is a definite user gesture — pre-warm the
  // AudioContext now so the first greeting plays the instant the audio
  // bytes arrive, instead of waiting on AudioContext.resume() at that point.
  if (avatarEnabled.value && avatarVoiceEnabled.value) {
    avatarPrewarm().catch(() => { /* prewarm is best-effort */ })
  }

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
    // Speak the greeting too when the avatar is on — without this the
    // session opened with the avatar visible but silent until the user
    // sent their first message, which felt like the bot "wasn't talking."
    // The greeting is the bot's first turn, so it should get the same
    // voice treatment as every subsequent reply.
    if (avatarEnabled.value && avatarVoiceEnabled.value && !document.hidden) {
      avatarSpeak(therapistGreeting.value).catch(() => { /* silent — text already showing */ })
    }
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
    const res = await api.post<{ content: string; message_index: number; session_messages_remaining: number; cost: number; mood?: CompanionMood; mood_intensity?: number }>(
      '/api/life/therapist/chat',
      { messages: apiMessages },
    )
    therapistMessages.value.push({ role: 'assistant', content: res.content })
    companionMood.value = res.mood ?? 'neutral'
    companionMoodIntensity.value = res.mood_intensity ?? 0.0
    if (avatarEnabled.value && avatarVoiceEnabled.value && !document.hidden) {
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
        // 429 covers two cases: daily session limit reached (detail mentions "session limit"),
        // or upstream Venice rate-limit ("busy right now"). Distinguish by detail text.
        const isSessionLimit = detail?.toLowerCase().includes('session limit')
        if (isSessionLimit) {
          therapistError.value = handleServiceError('Session Limit Reached', detail ?? 'You\'ve reached the session limit for today. Come back tomorrow!')
        } else {
          therapistError.value = handleServiceError('Wellness Bot Busy', detail ?? 'The Wellness Bot is busy right now. Your tokens were not charged. Try again in a moment.')
        }
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
  if (deletingNoteTimer) clearTimeout(deletingNoteTimer)
  deletingNote.value = null
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
// Stop voice the moment the tab loses visibility — the avatar shouldn't
// keep talking into an empty room. A reply that lands while we're hidden
// also stays silent (see avatarEnabled && !document.hidden guards above).
function onVisibilityChange() {
  if (document.hidden) avatarStop()
}

onMounted(async () => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  await Promise.all([
    fetchTherapistStatus(),
    fetchTherapistNotes(),
  ])
  loadingTherapist.value = false

  // Auto-open the session: skip the old "Start Session" gate so the user
  // lands straight on the avatar + chat. Daily-quota enforcement still
  // happens server-side on the chat endpoint, so opening the session
  // without a message doesn't burn quota.
  if (
    therapistAvailable.value &&
    therapistView.value === 'chat' &&
    !therapistSessionActive.value &&
    therapistStatus.value &&
    therapistStatus.value.sessions_remaining > 0
  ) {
    startTherapistSession()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  avatarStop()
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
        :class="therapistView === view.key || (therapistView === 'note-detail' && view.key === 'notes')
          ? 'tab-btn-active'
          : 'tab-btn'"
      >
        {{ view.label }}
      </button>
      <span v-if="therapistStatus" class="ml-auto text-xs text-txt-muted self-center tabular-nums">
        {{ therapistStatus.sessions_remaining }}/{{ therapistStatus.sessions_limit }} sessions left today
      </span>
    </div>

    <p v-if="therapistError" class="text-sm text-danger mb-4">{{ therapistError }}</p>

    <!-- ===== CHAT VIEW ===== -->
    <template v-if="therapistView === 'chat'">
      <!-- Quota-exhausted banner: the only path that doesn't render the chat. -->
      <div v-if="therapistStatus?.sessions_remaining === 0" class="glass-card p-8 text-center">
        <MessageCircleHeart :size="32" class="mx-auto mb-3 text-txt-muted" />
        <h3 class="text-base font-semibold text-txt-primary mb-1">No sessions left today</h3>
        <p class="text-sm text-txt-muted">Come back tomorrow to continue talking.</p>
      </div>

      <!-- Active session: chat. Fit to visible viewport so the input is
           anchored at the bottom and only the messages area scrolls.
           - 100dvh (dynamic) tracks mobile URL bar + soft keyboard so the
             input doesn't fall below the fold on iOS Safari.
           - 220px ≈ TopNav + page top padding + back-nav row + bottom
             padding (rough but stable enough for both mobile and desktop).
           No more "Start Session" gate — the session auto-opens on mount
           (see onMounted). The compact disclaimer + mood-before strip below
           preserves the legal copy and pre-session sentiment capture that
           used to live on the old start screen. -->
      <div v-else class="flex flex-col h-[calc(100dvh-220px)] min-h-[320px] max-h-[calc(100dvh-220px)]">
        <!-- Compact disclaimer + mood-before. Mood strip auto-collapses once
             a mood is picked or the conversation is underway. -->
        <div class="mb-3 space-y-2 text-xs">
          <div v-if="therapistDisclaimer" class="flex items-start gap-2 text-txt-muted leading-snug">
            <AlertTriangle :size="12" class="text-accent/80 mt-0.5 shrink-0" />
            <p>{{ therapistDisclaimer }}</p>
          </div>
          <div
            v-if="!therapistMoodBefore && therapistMessages.length <= 1"
            class="flex items-center gap-2 flex-wrap"
          >
            <span class="text-txt-muted">How are you feeling?</span>
            <div class="flex gap-1">
              <button
                v-for="mood in moods.slice(0, 6)"
                :key="mood.emoji"
                @click="therapistMoodBefore = mood.emoji"
                class="w-7 h-7 rounded-md flex items-center justify-center text-txt-muted hover:bg-surface-3 transition-colors"
              >
                <component :is="moodIcons[mood.emoji]" :size="15" v-if="moodIcons[mood.emoji]" />
              </button>
            </div>
          </div>
        </div>
        <!-- Avatar — when on, she's both visible AND speaks the replies.
             The bottom-right toggle hides her without leaving the session,
             same key as the Settings tab so both surfaces stay in sync. -->
        <div v-if="avatarEnabled" class="mb-3 rounded-2xl overflow-hidden border border-bdr/40 relative">
          <WellnessAvatar
            ref="avatarRef"
            :height="380"
            :mood="companionMood"
            :mood-intensity="companionMoodIntensity"
          />
          <!-- Status pill (top-left). Four honest states — the idle state
               used to say "Listening" which lied when the mic was off.
               Now: Muted (her voice output off), Speaking (TTS playing),
               Hearing you (mic actively capturing), Here (idle / present
               but not listening). The voice-input banner below the input
               bar covers the finer mic phases. -->
          <div
            class="absolute top-3 left-3 px-2.5 py-1 rounded-full bg-black/35 backdrop-blur-sm text-[11px] text-white/90 flex items-center gap-1.5 transition-opacity"
            :class="(avatarSpeaking || voicePhase === 'capturing') ? 'opacity-100' : 'opacity-60'"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="!avatarVoiceEnabled
                ? 'bg-red-400'
                : avatarSpeaking
                  ? 'bg-emerald-400 animate-pulse'
                  : voicePhase === 'capturing'
                    ? 'bg-rose-300 animate-pulse'
                    : 'bg-white/40'"
            ></span>
            {{ !avatarVoiceEnabled
                ? 'Muted'
                : avatarSpeaking
                  ? 'Speaking'
                  : voicePhase === 'capturing'
                    ? 'Hearing you'
                    : 'Here' }}
          </div>
          <!-- Privacy line (top-right): keeps the Venice-private framing
               visible — chat content never leaves Venice; voice in/out is
               processed by Whisper / Cartesia for audio bytes only. -->
          <div
            class="absolute top-3 right-12 px-2.5 py-1 rounded-full bg-black/35 backdrop-blur-sm text-[10px] text-white/75 flex items-center gap-1"
            title="Conversation stays in Venice (private). Voice audio bytes are processed by Whisper (STT) and Cartesia (TTS)."
          >
            <Lock :size="10" />
            <span class="hidden sm:inline">Venice-private chat</span>
            <span class="sm:hidden">Private</span>
          </div>
          <!-- Mute toggle (bottom-right, next to the close button). Decoupled
               from avatar visibility — keeps her on screen but silences TTS
               (and skips the Cartesia spend). -->
          <button
            @click="avatarVoiceEnabled = !avatarVoiceEnabled"
            class="absolute bottom-3 right-14 w-9 h-9 rounded-full bg-black/45 hover:bg-black/65 backdrop-blur-sm text-white/90 flex items-center justify-center transition-colors"
            :title="avatarVoiceEnabled ? 'Mute voice (avatar stays visible)' : 'Unmute voice'"
            :aria-label="avatarVoiceEnabled ? 'Mute voice' : 'Unmute voice'"
          >
            <Volume2 v-if="avatarVoiceEnabled" :size="16" />
            <VolumeX v-else :size="16" class="text-red-300" />
          </button>
          <!-- Avatar on/off toggle (bottom-right). Closes back to text-only
               wellness chat without leaving the session. -->
          <button
            @click="avatarEnabled = false"
            class="absolute bottom-3 right-3 w-9 h-9 rounded-full bg-black/45 hover:bg-black/65 backdrop-blur-sm text-white/90 flex items-center justify-center transition-colors"
            :title="'Hide avatar (chat continues without voice)'"
            :aria-label="'Hide avatar'"
          >
            <X :size="16" />
          </button>
          <!-- Live caption strip (bottom-center). Visible only while the user
               is actively speaking and we have interim text from the Web Speech
               API. Whisper still produces the canonical transcript that ends
               up as the chat bubble — this is purely visual feedback so the
               user sees motion as they talk. Empty on browsers without
               SpeechRecognition (Safari/iOS); the volume meter handles those. -->
          <div
            v-if="!voiceMuted && voiceInterim"
            class="absolute left-1/2 -translate-x-1/2 bottom-14 max-w-[80%] px-3 py-1.5 rounded-lg bg-black/55 backdrop-blur-sm text-white/90 text-sm text-center leading-snug pointer-events-none animate-fade-in"
          >
            {{ voiceInterim }}
          </div>
        </div>
        <!-- Floating "show avatar" pill when she's off. Inline so the user
             doesn't have to leave chat for Settings to bring her back. -->
        <button
          v-else
          @click="avatarEnabled = true"
          class="mb-3 self-end inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-2 hover:bg-surface-3 border border-bdr/60 text-xs text-txt-secondary transition-colors"
          title="Show avatar &amp; speak replies"
        >
          <User :size="14" />
          Show avatar
        </button>
        <!-- Messages — aria-live=polite so SR auto-announces new replies. -->
        <div
          class="flex-1 overflow-y-auto space-y-4 mb-4 pr-1"
          ref="chatContainer"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          aria-label="Wellness companion conversation"
        >
          <div
            v-for="(msg, i) in therapistMessages"
            :key="i"
            class="flex"
            :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
          >
            <div
              class="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed"
              :class="msg.role === 'user'
                ? 'bg-accent text-surface-0 rounded-br-md'
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
            aria-label="Show a different tip"
          >
            <RotateCw :size="12" />
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
            <div class="flex gap-1" role="radiogroup" aria-label="Session rating">
              <button
                v-for="star in [1, 2, 3, 4, 5]"
                :key="star"
                @click="therapistRating = therapistRating === star ? null : star"
                class="p-1 transition-colors"
                :class="therapistRating && star <= therapistRating ? 'text-accent' : 'text-surface-3 hover:text-accent/50'"
                role="radio"
                :aria-checked="!!(therapistRating && star <= therapistRating)"
                :aria-label="`${star} ${star === 1 ? 'star' : 'stars'}`"
              >
                <Star :size="20" :fill="therapistRating && star <= therapistRating ? 'currentColor' : 'none'" />
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
            <span class="text-xs text-txt-muted tabular-nums">{{ therapistMessagesRemaining }} messages left</span>
            <button
              @click="endTherapistSession()"
              :disabled="therapistEndingSession"
              class="ml-auto px-3 py-1.5 text-xs rounded-lg border border-bdr text-txt-muted hover:text-txt-primary hover:bg-surface-2 transition-colors disabled:opacity-40"
            >
              {{ therapistEndingSession ? 'Saving...' : 'End Session' }}
            </button>
          </div>
          <!-- Voice status — only renders when the loop is doing something.
               Muted = no banner; the mic button itself signals state. -->
          <div
            v-if="!voiceMuted"
            class="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg border animate-fade-in"
            :class="{
              'bg-danger/10 border-danger/30 text-danger': voicePhase === 'capturing',
              'bg-accent/10 border-accent/30 text-accent': voicePhase === 'transcribing',
              'bg-surface-2/60 border-bdr/60 text-txt-muted': voicePhase === 'listening' || voicePhase === 'paused',
            }"
          >
            <span
              class="w-2 h-2 rounded-full"
              :class="{
                'bg-danger animate-pulse': voicePhase === 'capturing',
                'bg-accent animate-pulse': voicePhase === 'transcribing',
                'bg-success animate-pulse': voicePhase === 'listening',
                'bg-txt-muted/60': voicePhase === 'paused',
              }"
            ></span>
            <span class="text-xs flex-1">
              <template v-if="voicePhase === 'capturing'">Capturing — pause to send</template>
              <template v-else-if="voicePhase === 'transcribing'">Transcribing…</template>
              <template v-else-if="voicePhase === 'paused'">Paused while she's speaking</template>
              <template v-else>Listening — just talk</template>
            </span>
            <!-- Volume meter — visible feedback that her ears are open. -->
            <div class="w-16 h-1.5 rounded-full bg-surface-3 overflow-hidden">
              <div
                class="h-full transition-[width] duration-75"
                :class="voicePhase === 'capturing' ? 'bg-danger' : 'bg-success'"
                :style="{ width: Math.round(voiceVolume * 100) + '%' }"
              ></div>
            </div>
          </div>
          <div class="flex gap-2">
            <textarea
              v-model="therapistInput"
              @keydown.enter.exact.prevent="sendTherapistMessage()"
              :placeholder="voiceMuted ? 'What\'s on your mind...' : (voicePhase === 'transcribing' ? 'Transcribing…' : 'Speak — or type instead')"
              rows="2"
              class="flex-1 bg-surface-2 border border-bdr rounded-xl px-4 py-3 text-sm text-txt-primary placeholder-txt-muted resize-none focus:outline-none focus:ring-1 focus:ring-accent/50"
              :disabled="therapistSending || therapistMessagesRemaining <= 0 || voicePhase === 'transcribing'"
            ></textarea>
            <!-- Voice mute/unmute — single source of truth. Muted = mic off
                 entirely. Unmuted = continuous VAD-segmented voice loop. -->
            <button
              v-if="voiceInputEnabled && voiceInputSupported"
              @click="toggleVoice()"
              :disabled="therapistSending || therapistMessagesRemaining <= 0"
              :class="[
                'self-end relative px-4 py-3 rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
                voiceMuted
                  ? 'bg-surface-3 text-txt-secondary hover:bg-surface-4 border border-bdr'
                  : voicePhase === 'capturing'
                    ? 'bg-danger text-surface-0 hover:opacity-90'
                    : voicePhase === 'transcribing'
                      ? 'bg-accent text-surface-0'
                      : 'bg-success text-surface-0 hover:opacity-90',
              ]"
              :aria-label="voiceMuted ? 'Unmute microphone' : 'Mute microphone'"
              :aria-pressed="!voiceMuted"
            >
              <Loader2 v-if="voicePhase === 'transcribing'" :size="18" class="animate-spin" />
              <MicOff v-else-if="voiceMuted" :size="18" />
              <Mic v-else :size="18" />
              <!-- Pulse ring when actively listening, so even at a glance the
                   user can tell she's hearing them. -->
              <span
                v-if="!voiceMuted && voicePhase !== 'transcribing'"
                class="absolute -inset-0.5 rounded-xl ring-2 pointer-events-none animate-ping"
                :class="voicePhase === 'capturing' ? 'ring-danger/60' : 'ring-success/60'"
              ></span>
            </button>
            <button
              @click="sendTherapistMessage()"
              :disabled="!therapistInput.trim() || therapistSending || therapistMessagesRemaining <= 0 || voicePhase === 'transcribing'"
              class="self-end px-4 py-3 rounded-xl bg-accent text-surface-0 hover:bg-accent-bright transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Send message"
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
            <!-- Two-step delete (bible §11) — first click arms confirm for 4s -->
            <template v-if="deletingNote !== note.id">
              <button
                @click.stop="armDeleteNote(note.id)"
                class="p-2 rounded-lg text-txt-muted/40 hover:text-danger hover:bg-danger/10 transition-all"
                aria-label="Delete note"
              >
                <Trash2 :size="14" />
              </button>
            </template>
            <template v-else>
              <div class="flex gap-1">
                <button
                  @click.stop="deleteTherapistNote(note.id)"
                  class="text-xs font-medium text-danger px-2 py-1 rounded ring-1 ring-danger/50 bg-danger/10 inline-flex items-center gap-1"
                >
                  <Trash2 :size="12" />
                  Confirm
                </button>
                <button
                  @click.stop="deletingNote = null"
                  class="text-xs text-txt-muted hover:text-txt-primary px-2 py-1 rounded"
                >Cancel</button>
              </div>
            </template>
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
        class="inline-flex items-center gap-1.5 text-sm text-accent hover:text-accent-bright mb-4"
        aria-label="Back to session notes"
      >
        <ArrowLeft :size="14" />
        <span>Back</span>
      </button>

      <div class="glass-card p-6 space-y-5">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-xs text-txt-muted">{{ formatDate(therapistCurrentNote.created_at) }}</p>
            <div v-if="therapistCurrentNote.mood_snapshot" class="mt-1">
              <span class="text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent">{{ therapistCurrentNote.mood_snapshot }}</span>
            </div>
          </div>
          <div class="flex gap-2 items-center">
            <button
              v-if="!therapistEditingNote"
              @click="startEditingNote()"
              class="p-1.5 rounded-lg text-txt-muted hover:text-accent hover:bg-accent/10 transition-colors"
              aria-label="Edit note"
            >
              <Pencil :size="16" />
            </button>
            <!-- Two-step delete (bible §11) — first click arms confirm for 4s -->
            <template v-if="deletingNote !== therapistCurrentNote.id">
              <button
                @click="armDeleteNote(therapistCurrentNote.id)"
                class="p-1.5 rounded-lg text-txt-muted hover:text-danger hover:bg-danger/10 transition-colors"
                aria-label="Delete note"
              >
                <Trash2 :size="16" />
              </button>
            </template>
            <template v-else>
              <button
                @click="deleteTherapistNote(therapistCurrentNote.id)"
                class="text-xs font-medium text-danger px-2 py-1 rounded ring-1 ring-danger/50 bg-danger/10 inline-flex items-center gap-1"
              >
                <Trash2 :size="12" />
                Confirm
              </button>
              <button
                @click="deletingNote = null"
                class="text-xs text-txt-muted hover:text-txt-primary px-2 py-1 rounded"
              >Cancel</button>
            </template>
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
            <button @click="saveNoteEdit()" class="px-4 py-1.5 text-sm rounded-lg bg-accent text-surface-0 hover:bg-accent-bright transition-colors">
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
