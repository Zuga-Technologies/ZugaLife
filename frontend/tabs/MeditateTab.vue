<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { api, ApiError, getToken } from '@core/api/client'
import { startAmbience, stopAmbience, pauseAmbience, resumeAmbience, setAmbienceVolume } from '../ambience'
import { meditationTypeIcons, ambienceIcons } from '../icons'
import { Download, Headphones } from 'lucide-vue-next'
import { useLifeShared, type GamificationData } from '../composables/useLifeShared'
import { playXpSound, playBadgeSound, playLevelUpSound } from '../composables/useCelebrationSounds'

const emit = defineEmits<{ (e: 'success'): void }>()

const {
  gamificationData,
  ALL_BADGES,
  celebration,
  handleInsufficientTokens,
  handleServiceError,
  notifyTokenSpend,
  fetchGamification,
  withCelebration,
  tokenLabel,
  timeAgo,
} = useLifeShared()

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
  { key: 'quick', label: 'Quick', sub: '~2 min' },
  { key: 'short', label: 'Short', sub: '~5 min' },
  { key: 'medium', label: 'Medium', sub: '~10 min' },
  { key: 'long', label: 'Long', sub: '~20 min' },
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
const transcriptContainer = ref<HTMLElement | null>(null)
let activeParagraphEl: HTMLElement | null = null

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

/** Parse transcript into timed segments using [PAUSE Xs] markers.
 *  Each segment gets an estimated start/end time based on character count
 *  proportional to total speech duration (total - silence). */
interface TranscriptSegment {
  text: string
  startTime: number
  endTime: number
}

const transcriptSegments = computed<TranscriptSegment[]>(() => {
  if (!medSession.value?.transcript) return []
  // Use the audio element's measured duration once loaded; otherwise fall
  // back to the session record's stored duration. Without this fallback the
  // transcript stayed empty until the user pressed play (which kicked the
  // audio metadata load that set medDurationSec for the first time).
  const totalDuration = medDurationSec.value || medSession.value.duration_seconds || 0
  if (!totalDuration) return []
  const raw = medSession.value.transcript
  const pausePattern = /\[PAUSE\s*(\d+)s?\]/gi

  // Split on pause markers, keep pause durations
  const texts: string[] = []
  const pauses: number[] = []
  let lastEnd = 0
  let match: RegExpExecArray | null
  while ((match = pausePattern.exec(raw)) !== null) {
    const chunk = raw.slice(lastEnd, match.index).trim()
    if (chunk) {
      texts.push(chunk)
      pauses.push(parseInt(match[1], 10))
    }
    lastEnd = match.index + match[0].length
  }
  const remainder = raw.slice(lastEnd).trim()
  if (remainder) {
    texts.push(remainder)
    pauses.push(0)
  }
  if (!texts.length) return []

  // Total silence from pause markers
  const totalSilence = pauses.reduce((a, b) => a + b, 0)
  // Speech duration = total audio minus silences
  const speechDuration = Math.max(totalDuration - totalSilence, 1)
  // Total chars across all segments (for proportional timing)
  const totalChars = texts.reduce((a, t) => a + t.length, 0) || 1

  const segments: TranscriptSegment[] = []
  let cursor = 0
  for (let i = 0; i < texts.length; i++) {
    const segSpeech = (texts[i].length / totalChars) * speechDuration
    const startTime = cursor
    const endTime = cursor + segSpeech
    segments.push({ text: texts[i], startTime, endTime })
    cursor = endTime + pauses[i]
  }
  return segments
})

const activeSegmentIndex = computed(() => {
  const t = medCurrentTime.value
  const segs = transcriptSegments.value
  if (!segs.length) return 0
  // Find the segment whose time range contains current playback time
  for (let i = segs.length - 1; i >= 0; i--) {
    if (t >= segs[i].startTime) return i
  }
  return 0
})

// Auto-scroll transcript to keep the active segment visible (throttled to avoid scroll jank)
let _lastScrollTime = 0
watch(activeSegmentIndex, () => {
  const now = performance.now()
  if (now - _lastScrollTime < 250) return  // max 4x/sec
  _lastScrollTime = now
  nextTick(() => {
    if (activeParagraphEl && transcriptContainer.value) {
      activeParagraphEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
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

/** Map backend error_message strings to user-friendly modal content */
function handleMeditationFailure(errorMsg: string | null, retryFn?: () => void): string {
  if (errorMsg === 'insufficient_tokens') {
    return handleInsufficientTokens('Meditation')
  }
  if (errorMsg?.includes('temporarily unavailable')) {
    return handleServiceError(
      'Service Temporarily Unavailable',
      'Our AI provider is experiencing issues. This usually resolves within a few minutes. Your tokens were not charged.',
      retryFn,
    )
  }
  if (errorMsg?.includes('timed out')) {
    return handleServiceError(
      'Generation Timed Out',
      'The meditation took too long to generate. Try a shorter duration, or try again in a moment.',
      retryFn,
    )
  }
  if (errorMsg?.includes('Could not reach')) {
    return handleServiceError(
      'Connection Issue',
      'We couldn\'t reach the AI service. Check your internet connection and try again.',
      retryFn,
    )
  }
  // Generic fallback — still show a modal, not raw text
  return handleServiceError(
    'Generation Failed',
    errorMsg || 'Something went wrong generating your meditation. Please try again.',
    retryFn,
  )
}

/** Poll a session until it becomes ready or failed. Shared by both
 *  fresh generation and resume-on-return flows. */
async function _pollUntilDone(sessionId: number) {
  const startTime = Date.now()
  let polls = 0

  while (true) {
    await new Promise(r => setTimeout(r, 3000))
    polls++

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
        notifyTokenSpend()
        await fetchMedRemaining()
        await fetchMedSessions()
        if (gamificationData.value) {
          celebration.setActionSource('meditation_complete')
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
        emit('success')
        return
      }

      if (session.status === 'failed') {
        medError.value = handleMeditationFailure(session.error_message)
        return
      }
    } catch {
      if (polls > 200) {
        medError.value = 'Generation is taking unusually long. Check session history later.'
        return
      }
    }
  }
}

/** Check for an in-progress meditation on mount. If one exists, resume
 *  the generating UI and poll until it finishes. */
async function checkInProgressMeditation() {
  try {
    const res = await api.get<{ session: MeditationSession | null }>('/api/life/meditation/in-progress')
    if (res.session) {
      medGenerating.value = true
      medGenStage.value = 'Resuming generation...'
      try {
        await _pollUntilDone(res.session.id)
      } finally {
        medGenerating.value = false
        medGenStage.value = null
      }
    }
  } catch { /* silent — non-critical */ }
}

/** Detect if the Zugabot Chrome extension is installed */
function hasZugaExtension(): boolean {
  return document.documentElement.hasAttribute('data-zugabot-extension')
}

/** Send a command to the extension via bridge.js */
function sendExtensionCommand(type: string, payload: Record<string, unknown> = {}) {
  document.dispatchEvent(new CustomEvent('zugabot:command', {
    detail: { type, payload },
  }))
}

/** Listen for extension meditation events */
let extensionMedListenersSetup = false
let extensionMedFallbackTimer: ReturnType<typeof setTimeout> | null = null
let extensionMedPollTimer: ReturnType<typeof setInterval> | null = null
let extensionMedResolved = false

function clearExtensionMedTimers() {
  if (extensionMedFallbackTimer) { clearTimeout(extensionMedFallbackTimer); extensionMedFallbackTimer = null }
  if (extensionMedPollTimer) { clearInterval(extensionMedPollTimer); extensionMedPollTimer = null }
}

function handleExtensionMedComplete(session?: MeditationSession) {
  if (extensionMedResolved) return
  extensionMedResolved = true
  clearExtensionMedTimers()
  medGenerating.value = false
  medGenStage.value = null
  notifyTokenSpend()
  fetchMedSessions().then(() => {
    if (session) {
      medSession.value = session
      medMoodAfter.value = null
      medView.value = 'player'
      medSuccess.value = 'Meditation generated!'
      setTimeout(() => { medSuccess.value = null }, 2000)
      fetchMedRemaining()
      setTimeout(() => loadAndPlayAudio(), 300)
    }
  })
}

function setupExtensionMedListeners() {
  if (extensionMedListenersSetup) return
  extensionMedListenersSetup = true

  document.addEventListener('zugabot:response', ((e: CustomEvent) => {
    const detail = e.detail
    if (detail.type === 'meditation:progress') {
      medGenStage.value = detail.stage
    }
    if (detail.type === 'meditation:complete') {
      handleExtensionMedComplete(detail.session)
    }
    if (detail.type === 'meditation:error') {
      if (extensionMedResolved) return
      extensionMedResolved = true
      clearExtensionMedTimers()
      medGenerating.value = false
      medGenStage.value = null
      const err = detail.error || 'Extension generation failed'
      // Map extension errors to proper modals
      if (err.includes('402') || err.toLowerCase().includes('insufficient') || err.toLowerCase().includes('token')) {
        medError.value = handleInsufficientTokens('Meditation')
      } else if (err.includes('500') || err.includes('503') || err.toLowerCase().includes('api error')) {
        medError.value = handleServiceError(
          'Service Temporarily Unavailable',
          'Our AI provider is experiencing issues. This usually resolves within a few minutes. Your tokens were not charged.',
          startMeditation,
        )
      } else if (err.toLowerCase().includes('timeout') || err.toLowerCase().includes('timed out')) {
        medError.value = handleServiceError(
          'Generation Timed Out',
          'The meditation took too long to generate. Try a shorter duration, or try again in a moment.',
          startMeditation,
        )
      } else if (err.toLowerCase().includes('network') || err.toLowerCase().includes('fetch')) {
        medError.value = handleServiceError(
          'Connection Issue',
          'We couldn\'t reach the AI service. Check your internet connection and try again.',
          startMeditation,
        )
      } else {
        medError.value = handleServiceError(
          'Generation Failed',
          'Something went wrong generating your meditation. Please try again.',
          startMeditation,
        )
      }
    }
  }) as EventListener)
}

/** Poll server for a newly completed session as fallback when the
 *  extension's completion event gets lost (service worker sleep, tab
 *  messaging failure, etc.). Records the session count before generation
 *  starts, then detects when a new "ready" session appears. */
function startExtensionMedFallbackPoll() {
  extensionMedResolved = false
  clearExtensionMedTimers()

  const beforeCount = medSessions.value.length

  // Poll every 5s — check if a new session appeared on the server
  extensionMedPollTimer = setInterval(async () => {
    if (extensionMedResolved) { clearExtensionMedTimers(); return }
    try {
      const res = await api.get<MeditationListResponse>('/api/life/meditation/sessions')
      if (res.sessions.length > beforeCount) {
        const newest = res.sessions[0]
        if (newest) {
          // Fetch the full session object (brief doesn't have transcript/audio)
          const full = await api.get<MeditationSession>(`/api/life/meditation/sessions/${newest.id}`)
          if (full.status === 'ready') {
            medSessions.value = res.sessions
            medTotal.value = res.total
            handleExtensionMedComplete(full)
          }
        }
      }
    } catch { /* silent — keep polling */ }
  }, 5000)

  // Hard timeout: 5 minutes — give up and show error
  extensionMedFallbackTimer = setTimeout(() => {
    if (extensionMedResolved) return
    extensionMedResolved = true
    clearExtensionMedTimers()
    medGenerating.value = false
    medGenStage.value = null
    medError.value = 'Generation timed out. Check your meditation history — it may have completed.'
  }, 5 * 60 * 1000)
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

  // Try extension-based generation first (runs on user's PC, saves server costs)
  if (hasZugaExtension()) {
    setupExtensionMedListeners()
    medGenStage.value = 'Starting via extension...'
    sendExtensionCommand('meditation:generate', payload)
    // Start fallback poll — if the extension event gets lost (service worker
    // sleep, tab messaging failure), the poll catches the completed session
    startExtensionMedFallbackPoll()
    return
  }

  // Server-side generation
  try {
    const stub = await api.post<MeditationSession>('/api/life/meditation/generate', payload)

    if (stub.status === 'failed') {
      medError.value = handleMeditationFailure(stub.error_message)
      return
    }

    await _pollUntilDone(stub.id)
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 402) {
        medError.value = handleInsufficientTokens('Meditation')
      } else if (e.status === 409) {
        medError.value = handleServiceError('Already Generating', detail ?? 'A meditation is already being generated. Please wait for it to finish.')
      } else if (e.status === 429) {
        medError.value = handleServiceError('Daily Limit Reached', detail ?? 'You\'ve used all your meditation sessions for today. Come back tomorrow for more!')
      } else if (e.status === 503) {
        medError.value = handleServiceError('Service Unavailable', 'Meditation generation is temporarily unavailable. Please try again later.')
      } else if (e.status >= 500) {
        medError.value = handleServiceError('Server Error', 'Something went wrong on our end. Your tokens were not charged. Please try again.', startMeditation)
      } else {
        medError.value = handleServiceError('Error', detail ?? 'Something went wrong. Please try again.')
      }
    } else {
      medError.value = handleServiceError('Connection Issue', 'We couldn\'t reach the server. Check your internet connection and try again.', startMeditation)
    }
  } finally {
    medGenerating.value = false
    medGenStage.value = null
  }
}

function startMeditation() {
  generateMeditation()
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
            api.post(`/api/life/meditation/sessions/${medSession.value!.id}/complete`),
            'meditation_complete'
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

// --- Meditation download & ZugaAudio integration ---
const showMedActionMenu = ref(false)
const medSendingToAudio = ref(false)

async function downloadMeditationAudio(session?: MeditationSession | null) {
  const s = session ?? medSession.value
  if (!s) return
  try {
    const token = getToken()
    const res = await fetch(`/api/life/meditation/audio/${s.audio_filename}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('Audio fetch failed')
    const blob = await res.blob()
    const date = new Date(s.created_at).toISOString().slice(0, 10)
    const safeTitle = (s.title || 'meditation').replace(/[^a-zA-Z0-9\s-]/g, '').trim()
    const filename = `ZugaLife - ${safeTitle} - ${date}.mp3`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    medError.value = 'Download failed'
  }
}

async function sendToZugaAudio() {
  if (!medSession.value || medSendingToAudio.value) return
  medSendingToAudio.value = true
  showMedActionMenu.value = false
  medError.value = null
  try {
    const token = getToken()
    // Fetch the meditation audio blob
    const audioRes = await fetch(`/api/life/meditation/audio/${medSession.value.audio_filename}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!audioRes.ok) throw new Error('Audio fetch failed')
    const blob = await audioRes.blob()

    // Upload to ZugaAudio
    const formData = new FormData()
    const safeTitle = (medSession.value.title || 'meditation').replace(/[^a-zA-Z0-9\s-]/g, '').trim()
    formData.append('file', blob, `${safeTitle}.mp3`)
    const uploadRes = await fetch('/api/audio/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    })
    if (!uploadRes.ok) throw new Error('Upload to ZugaAudio failed')
    const clip = await uploadRes.json()

    // Create a project in ZugaAudio with the clip on the master track
    const date = new Date(medSession.value.created_at).toISOString().slice(0, 10)
    const projectRes = await fetch('/api/audio/projects', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ title: `${safeTitle} - ${date}` }),
    })
    if (!projectRes.ok) throw new Error('Project creation failed')
    const project = await projectRes.json()

    // Update the project timeline to include the uploaded clip on the master track
    const masterTrack = project.timeline?.tracks?.[0]
    if (masterTrack) {
      masterTrack.clips = [{
        id: clip.clip_id,
        name: `${safeTitle}.mp3`,
        startTime: 0,
        duration: clip.duration,
        inPoint: 0,
        outPoint: clip.duration,
        volume: 1.0,
        fadeIn: 0,
        fadeOut: 0,
        waveformPeaks: clip.waveform_peaks || [],
      }]
      await fetch(`/api/audio/projects/${project.id}/timeline`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ tracks: project.timeline.tracks }),
      })
    }

    // Navigate to ZugaAudio with the project open
    window.location.href = `/audio?project=${project.id}`
  } catch {
    medError.value = 'Failed to send to ZugaAudio'
  } finally {
    medSendingToAudio.value = false
  }
}

async function downloadMedHistoryAudio(brief: MeditationBrief) {
  try {
    const full = await api.get<MeditationSession>(`/api/life/meditation/sessions/${brief.id}`)
    await downloadMeditationAudio(full)
  } catch {
    medError.value = 'Download failed'
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
// LIFECYCLE
// ============================

onMounted(async () => {
  await Promise.all([
    fetchMedRemaining(),
    fetchMedSessions(),
  ])
  loadingMeditation.value = false
  await checkInProgressMeditation()
})

onUnmounted(() => {
  stopAudio()
  clearExtensionMedTimers()
})
</script>

<template>
  <div>
    <!-- Sub-nav -->
    <div class="flex gap-3 mb-6">
      <button
        v-for="view in [
          { key: 'new', label: 'New Session' },
          { key: 'history', label: 'History' },
        ] as { key: MedView; label: string }[]"
        :key="view.key"
        @click="medError = null; medView = view.key; if (view.key === 'history') fetchMedSessions()"
        class="px-4 py-2.5 text-xs font-medium rounded-lg transition-colors"
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

    <!-- Extension status banner -->
    <div v-if="medView === 'new' && !medGenerating" class="mb-4 px-3 py-2 rounded-lg text-xs flex items-center gap-2"
      :class="hasZugaExtension() ? 'bg-accent-alt/10 text-accent-alt-bright' : 'bg-surface-2 text-txt-muted'"
    >
      <template v-if="hasZugaExtension()">
        <span class="w-2 h-2 rounded-full bg-accent-alt animate-pulse" />
        Extension active — meditation generates in the background, even if you leave this page.
      </template>
      <template v-else>
        <span class="w-2 h-2 rounded-full bg-txt-muted/50" />
        Install the <a href="https://zugabot.ai/extension" target="_blank" rel="noopener noreferrer" class="text-accent hover:underline">Zugabot extension</a> for background generation on PC.
      </template>
    </div>

    <!-- ===== NEW SESSION VIEW ===== -->
    <template v-if="medView === 'new'">
      <!-- Options — disabled while generating -->
      <div :class="{ 'opacity-50 pointer-events-none select-none': medGenerating }">
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
            class="flex-1 py-2 rounded-lg font-medium transition-all duration-150 flex flex-col items-center"
            :class="medLength === opt.key
              ? 'bg-accent text-white'
              : 'glass-card text-txt-muted hover:text-txt-primary'"
          >
            <span class="text-sm">{{ opt.label }}</span>
            <span class="text-[10px] opacity-70">{{ opt.sub }}</span>
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

      </div><!-- /options wrapper -->

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

    <!-- ===== PLAYER VIEW =====
         Back arrow removed — the 'New session' sub-nav button already returns
         here. View slides in from the right so the transition reads as a
         step forward into the session, not a fresh page load. -->
    <template v-if="medView === 'player' && medSession">
      <div class="med-view-slide-in">
      <!-- Session card -->
      <div class="glass-card p-6 mb-4">
        <div class="flex items-start justify-between mb-3">
          <div>
            <h2 class="text-lg font-semibold text-txt-primary">{{ medSession.title }}</h2>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-xs text-txt-muted">{{ getMedTypeLabel(medSession.type) }}</span>
              <span class="text-xs text-txt-muted">{{ Math.floor(medSession.duration_seconds / 60) }}:{{ String(medSession.duration_seconds % 60).padStart(2, '0') }}</span>
              <span class="text-xs text-txt-muted">{{ tokenLabel(medSession.cost) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              @click="toggleMedFavorite"
              class="text-xl transition-colors"
              :class="medSession.is_favorite ? 'text-accent' : 'text-txt-muted hover:text-accent'"
            >
              {{ medSession.is_favorite ? '&#9733;' : '&#9734;' }}
            </button>
            <div class="relative">
              <button
                @click="showMedActionMenu = !showMedActionMenu"
                class="text-txt-muted hover:text-accent transition-colors p-1"
                title="More actions"
              >
                <Download :size="16" />
              </button>
              <div v-if="showMedActionMenu" class="absolute right-0 top-full mt-1 glass-card p-1 rounded-lg shadow-lg z-20 min-w-[180px] max-w-[calc(100vw-2rem)]">
                <button
                  @click="showMedActionMenu = false; downloadMeditationAudio()"
                  class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-white/5 px-3 py-2 rounded transition-colors flex items-center gap-2"
                >
                  <Download :size="12" />
                  Download MP3
                </button>
                <button
                  @click="sendToZugaAudio()"
                  :disabled="medSendingToAudio"
                  class="w-full text-left text-xs text-txt-secondary hover:text-txt-primary hover:bg-white/5 px-3 py-2 rounded transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  <Headphones :size="12" />
                  {{ medSendingToAudio ? 'Sending...' : 'Edit in ZugaAudio' }}
                </button>
              </div>
            </div>
          </div>
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
      <div ref="transcriptContainer" class="glass-card p-5 mb-4 max-h-64 overflow-y-auto scroll-smooth">
        <h3 class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-3">Transcript</h3>
        <div class="space-y-3">
          <p
            v-for="(seg, i) in transcriptSegments"
            :key="i"
            :ref="el => { if (i === activeSegmentIndex) activeParagraphEl = el as HTMLElement }"
            class="text-sm leading-relaxed transition-all duration-500"
            :class="i === activeSegmentIndex
              ? 'text-txt-primary font-medium'
              : i < activeSegmentIndex
                ? 'text-txt-secondary'
                : 'text-txt-muted/40'"
          >
            {{ seg.text }}
          </p>
        </div>
      </div>

      <!-- Post-session mood removed — cluttered the meditation experience -->
      </div>
    </template>

    <!-- ===== HISTORY VIEW ===== -->
    <template v-if="medView === 'history'">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-txt-primary">Past Sessions</h2>
        <button
          @click="medShowFavoritesOnly = !medShowFavoritesOnly"
          class="text-sm transition-colors"
          :class="medShowFavoritesOnly ? 'text-accent' : 'text-txt-muted hover:text-txt-primary'"
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
              <span v-if="s.is_favorite" class="text-accent text-xs">&#9733;</span>
            </div>
          </div>
          <button
            @click.stop="downloadMedHistoryAudio(s)"
            class="text-txt-muted hover:text-accent transition-colors px-1 self-center"
            title="Download MP3"
          >
            <Download :size="14" />
          </button>
          <button
            @click.stop="deleteMedSession(s.id)"
            class="text-xs text-txt-muted hover:text-red-400 transition-colors px-1 self-center"
          >
            &times;
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Slide-in for the meditation player view — smoother than a hard cut
   when the user generates a session and the view swaps from 'new' to
   'player'. ~280ms quart-out so it reads as a step forward. */
.med-view-slide-in {
  animation: med-slide-in 280ms cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes med-slide-in {
  from { opacity: 0; transform: translateX(16px); }
  to   { opacity: 1; transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .med-view-slide-in { animation: none; }
}
</style>
