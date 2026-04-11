<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ApiError } from '@core/api/client'
import {
  Send, Settings, Zap, Flame as FlameIcon, Brain as BrainIcon, Target, CheckCircle2, Star,
  Trophy, Lock, ChevronRight, CalendarDays, TrendingUp, BookOpen,
  MessageCircleHeart, Wind, Meh,
} from 'lucide-vue-next'
import { moodIcons, badgeIcons, xpSourceIcons, prestigeIcons, getIcon } from '../icons'
import ShareableCard from '../components/ShareableCard.vue'
import AnalyticsDashboard from '../AnalyticsDashboard.vue'
import InsightCard from '../components/InsightCard.vue'
import WeeklyNarrative from '../components/WeeklyNarrative.vue'
import ThemeRenderer from '../components/themes/ThemeRenderer.vue'
import { applyPreset } from '../theme-presets'
import { useLifeShared, type GamificationData } from '../composables/useLifeShared'
import { useNotifications } from '../composables/useNotifications'
import {
  playPrestigeSound,
} from '../composables/useCelebrationSounds'

// ── Props & Emits ───────────────────────────────────────────────
const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const emit = defineEmits<{
  (e: 'navigate', tab: string): void
  (e: 'open-settings'): void
}>()

// ── Shared composable ───────────────────────────────────────────
const {
  gamificationData,
  moods,
  ALL_BADGES,
  withCelebration,
  fetchGamification,
  celebration,
  activePresetId,
  parseUTC,
  timeAgo,
  stripEmoji,
  formatDashboardDate,
  formatDeadline,
} = useLifeShared()

// ── Notifications ───────────────────────────────────────────────
const notif = useNotifications()

// ============================
// DASHBOARD DATA
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
  loadingDashboard.value = true
  try {
    const res = await api.get<DashboardData>('/api/life/dashboard')
    dashboardData.value = res
  } catch (e) {
    console.error('Dashboard fetch failed:', e)
  } finally {
    loadingDashboard.value = false
  }
}

// ============================
// ZUGATHEMES
// ============================

interface InstalledTheme {
  id: string
  theme_id: string
  studio: string
  pos_x: number
  pos_y: number
  pos_w: number
  pos_h: number
  enabled: boolean
  theme: {
    id: string
    title: string
    html: string
    css: string | null
    js: string
    permissions: Array<{ key: string; type: string; description: string }>
    [key: string]: unknown
  }
}

const installedThemes = ref<InstalledTheme[]>([])

async function fetchInstalledThemes() {
  try {
    const res = await api.get<InstalledTheme[]>('/api/life/themes/my/installed?studio=life')
    installedThemes.value = res.filter(t => t.enabled)
  } catch {
    // Themes are non-critical — don't block dashboard
  }
}

async function uninstallTheme(installId: string) {
  try {
    await api.delete(`/api/life/themes/install/${installId}`)
    installedThemes.value = installedThemes.value.filter(t => t.id !== installId)
  } catch (e) {
    console.error('Theme uninstall failed:', e)
  }
}

// ============================
// CUSTOM STUDIO COLORS (Restyle)
// ============================

async function applyCustomColors() {
  try {
    const settings = await api.get<{ custom_colors?: string | null; theme_preset?: string }>('/api/life/settings')

    // Apply theme preset (color scheme + typography + mood icons)
    if (settings.theme_preset && settings.theme_preset !== activePresetId.value) {
      activePresetId.value = settings.theme_preset
      applyPreset(settings.theme_preset)
    }

    // Legacy custom_colors is now handled by the theme overrides system
    // (Settings > My Themes). Remove any leftover restyle tag.
    document.getElementById('zugabot-restyle')?.remove()
  } catch {
    // Non-critical — fail silently
  }
}

// BroadcastChannel: cross-tab/cross-page theme + restyle events
const themeBroadcast = new BroadcastChannel('zugatheme')
themeBroadcast.onmessage = (e) => {
  if (e.data?.type === 'installed') fetchInstalledThemes()
  if (e.data?.type === 'restyled') applyCustomColors()
}

// ============================
// GAMIFICATION — PRESTIGE
// ============================

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

// ============================
// SHARE CARD
// ============================

const showShareCard = ref(false)

const shareCardData = computed(() => {
  const gam = gamificationData.value
  const dash = dashboardData.value
  if (!gam) return null

  let topMood: { emoji: string; label: string } | null = null
  if (dash?.mood?.recent?.length) {
    const counts: Record<string, { emoji: string; label: string; count: number }> = {}
    for (const m of dash.mood.recent) {
      const key = m.emoji
      if (!counts[key]) counts[key] = { emoji: m.emoji, label: m.label, count: 0 }
      counts[key].count++
    }
    const sorted = Object.values(counts).sort((a, b) => b.count - a.count)
    if (sorted.length > 0) topMood = { emoji: sorted[0].emoji, label: sorted[0].label }
  }

  return {
    displayName: dash?.greeting?.replace(/^Good (morning|afternoon|evening)(, )?/, '') || '',
    level: gam.xp.level,
    levelName: gam.xp.level_name,
    totalXp: gam.xp.total_xp,
    currentStreak: gam.xp.current_streak_days,
    longestStreak: gam.xp.longest_streak_days,
    badgeCount: gam.badges.length,
    topBadges: gam.badges.slice(-6).map(b => ({ emoji: b.emoji, title: b.title })),
    moodCount: dash?.mood?.total || 0,
    topMood,
    journalCount: dash?.journal?.total || 0,
    meditationCount: dash?.meditation?.total_sessions || 0,
    meditationMinutes: dash?.meditation?.total_minutes || 0,
    habitCompletionRate: dash?.habits?.completion_rate || 0,
    goalsCompleted: dash?.goals?.completed || 0,
    prestigeLevel: gam.xp.prestige_level,
    date: dash?.date || new Date().toISOString().slice(0, 10),
  }
})

// ============================
// INSIGHT CARDS
// ============================

interface InsightCardData {
  key: string
  title: string
  content: string
  category: string
}

const insightCards = ref<InsightCardData[]>([])

async function fetchInsightCards() {
  try {
    insightCards.value = await api.get<InsightCardData[]>('/api/life/gamification/insights')
  } catch { /* silent */ }
}

async function dismissInsight(key: string) {
  insightCards.value = insightCards.value.filter(c => c.key !== key)
  try { await api.post(`/api/life/gamification/insights/${key}/dismiss`) } catch { /* silent */ }
}

// ============================
// DASHBOARD MOOD PICKER
// ============================

const dashMoodNote = ref('')
const dashMoodSubmitting = ref(false)
const dashMoodSuccess = ref<string | null>(null)
const dashMoodError = ref<string | null>(null)
const dashMoodCooldownUntil = ref<string | null>(null)
const dashBreathworkSuggestion = ref<string | null>(null)

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
      api.post<{ entry: { emoji: string; label: string }; streak: number; today_count: number; suggestion: { type: string; message: string } | null }>('/api/life/mood', {
        emoji,
        note: dashMoodNote.value.trim() || null,
      }), 'mood_log'
    )
    dashMoodSuccess.value = `${res.entry.label} logged! (${res.today_count}/4 today)`
    dashMoodNote.value = ''
    setTimeout(() => { dashMoodSuccess.value = null }, 3000)
    if (res.suggestion?.type === 'breathwork') {
      dashBreathworkSuggestion.value = res.suggestion.message
    } else {
      dashBreathworkSuggestion.value = null
    }
    // Set cooldown for 6 hours from now
    dashMoodCooldownUntil.value = new Date(Date.now() + 6 * 3600000).toISOString()
    await fetchDashboard()
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
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

// ============================
// LIFECYCLE
// ============================

onMounted(async () => {
  await Promise.all([
    fetchDashboard(),
    fetchGamification(),
    fetchInstalledThemes(),
    fetchInsightCards(),
    applyCustomColors(),
  ])

  // Listen for theme events from ThemeBridge
  window.addEventListener('zugatheme:celebrate', ((e: CustomEvent) => {
    const type = e.detail?.type || 'confetti'
    if (type === 'confetti') celebration.triggerConfetti()
  }) as EventListener)

  window.addEventListener('zugatheme:installed', () => {
    fetchInstalledThemes()
  })

  window.addEventListener('zugatheme:notify', ((e: CustomEvent) => {
    const { message } = e.detail || {}
    if (message) celebration.pushToast({ type: 'info', message, duration: 3000 })
  }) as EventListener)
})
</script>

<template>
  <div>
    <!-- Share Card Modal -->
    <ShareableCard
      v-if="showShareCard && shareCardData"
      :data="shareCardData"
      @close="showShareCard = false"
    />

    <!-- ===== DASHBOARD TAB ===== -->
    <div v-if="loadingDashboard" class="animate-fade-in">
      <!-- Skeleton: Greeting -->
      <div class="flex items-start justify-between mb-8">
        <div class="inline-block px-5 py-3 rounded-2xl bg-surface-0/80">
          <div class="skeleton-pulse h-3 w-32 rounded mb-2"></div>
          <div class="skeleton-pulse h-7 w-56 rounded mb-2"></div>
          <div class="skeleton-pulse h-3 w-44 rounded"></div>
        </div>
        <div class="skeleton-pulse w-10 h-10 rounded-xl"></div>
      </div>

      <!-- Skeleton: XP bar -->
      <div class="glass-card p-5 mb-6">
        <div class="flex items-center gap-3">
          <div class="skeleton-pulse w-12 h-12 rounded-2xl flex-shrink-0"></div>
          <div class="flex-1">
            <div class="flex justify-between mb-1">
              <div class="skeleton-pulse h-3 w-28 rounded"></div>
              <div class="skeleton-pulse h-3 w-16 rounded"></div>
            </div>
            <div class="skeleton-pulse w-full h-2 rounded-full"></div>
          </div>
          <div class="skeleton-pulse w-10 h-10 rounded-lg flex-shrink-0"></div>
        </div>
      </div>

      <!-- Skeleton: Mood + Challenges + Narrative row -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div class="glass-card p-5">
          <div class="skeleton-pulse h-4 w-36 rounded mb-3"></div>
          <div class="grid grid-cols-3 gap-2 mb-3">
            <div v-for="i in 6" :key="i" class="skeleton-pulse h-14 rounded-xl"></div>
          </div>
          <div class="skeleton-pulse h-3 w-24 rounded"></div>
        </div>
        <div class="glass-card p-5">
          <div class="skeleton-pulse h-4 w-32 rounded mb-3"></div>
          <div class="space-y-2">
            <div v-for="i in 3" :key="i" class="skeleton-pulse h-12 rounded-xl"></div>
          </div>
        </div>
        <div class="glass-card p-5">
          <div class="skeleton-pulse h-4 w-36 rounded mb-3"></div>
          <div class="skeleton-pulse h-3 w-full rounded mb-2"></div>
          <div class="skeleton-pulse h-3 w-4/5 rounded mb-2"></div>
          <div class="skeleton-pulse h-3 w-3/4 rounded"></div>
        </div>
      </div>

      <!-- Skeleton: Module Cards Grid -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">
        <div v-for="i in 3" :key="i" class="glass-card p-5">
          <div class="flex items-center gap-2.5 mb-4">
            <div class="skeleton-pulse w-9 h-9 rounded-xl"></div>
            <div class="skeleton-pulse h-4 w-20 rounded"></div>
          </div>
          <div class="skeleton-pulse h-7 w-16 rounded mb-3"></div>
          <div class="skeleton-pulse h-2 w-full rounded-full mb-3"></div>
          <div class="flex gap-1.5">
            <div v-for="j in 3" :key="j" class="skeleton-pulse h-5 w-16 rounded-md"></div>
          </div>
        </div>
      </div>
    </div>

    <template v-else-if="dashboardData">
      <!-- Greeting + settings gear (hidden when embedded in ZugaApp — dashboard already greets) -->
      <div class="flex items-start justify-between mb-8 animate-fade-in">
        <div v-if="!props.embedded" class="inline-block px-5 py-3 rounded-2xl bg-surface-0/80">
          <p class="text-sm text-txt-muted mb-1">{{ formatDashboardDate(dashboardData.date) }}</p>
          <h2 class="text-2xl font-bold text-txt-primary tracking-tight">{{ dashboardData.greeting }}</h2>
          <p class="text-sm text-txt-secondary mt-1.5">Here's your week at a glance.</p>
        </div>
        <div v-else></div>
        <div class="flex items-center gap-2">
          <button
            v-if="!props.embedded && gamificationData"
            @click="showShareCard = true"
            class="p-2.5 rounded-xl bg-surface-0/80 border border-bdr text-txt-secondary transition-colors hover:text-accent hover:border-accent/40"
            title="Share your progress"
          >
            <Send :size="18" />
          </button>
          <button
            v-if="!props.embedded"
            @click="emit('open-settings')"
            class="p-2.5 rounded-xl bg-surface-0/80 border border-bdr text-txt-secondary transition-colors hover:text-txt-primary hover:bg-surface-3/70"
            title="Settings"
          >
            <Settings :size="18" />
          </button>
        </div>
      </div>

      <!-- XP + Level + Streak Bar -->
      <div v-if="gamificationData" class="glass-card p-5 mb-6 animate-fade-in">
        <div class="flex items-center gap-3">
          <!-- Level badge + prestige stars -->
          <div class="flex-shrink-0 flex flex-col items-center gap-0.5">
            <div class="relative">
              <div class="w-12 h-12 rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center"
                :class="{ 'prestige-glow': gamificationData.xp.prestige_level > 0 }">
                <span class="text-lg font-bold text-accent">{{ gamificationData.xp.level }}</span>
              </div>
              <!-- Prestige stars -->
              <div v-if="gamificationData.xp.prestige_level > 0"
                class="absolute -top-1.5 -right-1.5 flex items-center gap-px">
                <span v-for="i in Math.min(gamificationData.xp.prestige_level, 5)" :key="i"
                  class="text-[8px] prestige-star">&#11088;</span>
                <span v-if="gamificationData.xp.prestige_level > 5"
                  class="text-[7px] font-bold text-accent-bright">+{{ gamificationData.xp.prestige_level - 5 }}</span>
              </div>
            </div>
            <span class="text-[10px] text-txt-muted leading-none">{{ gamificationData.xp.level_name }}</span>
          </div>

          <!-- XP progress -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-1.5">
                <Zap :size="12" class="text-accent" />
                <span class="text-xs font-semibold text-txt-primary">{{ gamificationData.xp.xp_progress_in_level.toLocaleString() }} / {{ gamificationData.xp.xp_for_next_level.toLocaleString() }} XP</span>
              </div>
              <div class="flex items-center gap-1.5">
                <span v-if="gamificationData.xp.prestige_multiplier > 1"
                  class="text-[9px] font-bold text-accent-alt-bright bg-accent-alt/20 px-1 rounded multiplier-pulse">
                  P{{ gamificationData.xp.prestige_level }} +{{ Math.round((gamificationData.xp.prestige_multiplier - 1) * 100) }}%
                </span>
                <span class="text-[10px] text-txt-muted">{{ gamificationData.xp.total_xp.toLocaleString() }} total</span>
              </div>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-2 overflow-hidden">
              <div
                class="h-2 rounded-full transition-all duration-700 ease-out"
                :class="gamificationData.xp.can_prestige
                  ? 'bg-gradient-to-r from-accent-alt via-accent to-accent-alt prestige-bar-shimmer'
                  : 'bg-gradient-to-r from-accent to-accent-bright'"
                :style="{ width: Math.min(100, Math.round((gamificationData.xp.xp_progress_in_level / gamificationData.xp.xp_for_next_level) * 100)) + '%' }"
              ></div>
            </div>
          </div>

          <!-- Consistency (reframed from streak) -->
          <div class="flex-shrink-0 flex flex-col items-center gap-0.5">
            <div class="flex items-center gap-1">
              <FlameIcon :size="16" class="text-accent" />
              <span class="text-sm font-bold text-txt-primary">{{ gamificationData.xp.consistency_30d }}/30</span>
            </div>
            <div
              v-if="gamificationData.xp.streak_multiplier > 1"
              class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent/20 text-accent leading-none multiplier-pulse"
            >
              {{ gamificationData.xp.streak_multiplier }}x
            </div>
            <span v-else class="text-[10px] text-txt-muted leading-none">consistency</span>
            <div
              v-if="gamificationData.xp.streak_freezes > 0"
              class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-info/15 text-info leading-none"
              :title="`${gamificationData.xp.streak_freezes} streak freeze${gamificationData.xp.streak_freezes > 1 ? 's' : ''}`"
            >
              🧊 {{ gamificationData.xp.streak_freezes }}
            </div>
          </div>
        </div>

        <!-- Prestige Available Banner -->
        <div v-if="gamificationData.xp.can_prestige"
          class="mt-3 pt-3 border-t border-bdr/50">
          <div class="flex items-center gap-3 p-3 rounded-xl bg-gradient-to-r from-accent-alt/10 via-accent/10 to-accent-alt/10 border border-accent-alt/20 prestige-banner-glow">
            <div class="flex-1">
              <p class="text-sm font-bold text-accent-alt-bright">Prestige Available!</p>
              <p class="text-[10px] text-txt-muted mt-0.5">Reset to Lv.1 for a permanent +5% XP bonus and a unique badge</p>
            </div>
            <button
              @click="doPrestige"
              :disabled="prestigeLoading"
              class="px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-accent-alt-dim to-accent hover:from-accent-alt hover:to-accent-bright transition-all active:scale-95 disabled:opacity-50 min-h-[36px]"
            >
              {{ prestigeLoading ? 'Ascending...' : 'Prestige' }}
            </button>
          </div>
        </div>

        <!-- Notification prompt (show after streak >= 3 or has badges, not on first visit) -->
        <div
          v-if="notif.shouldShowPrompt() && (gamificationData.xp.current_streak_days >= 3 || gamificationData.badges.length >= 1)"
          class="mt-3 pt-3 border-t border-bdr/50"
        >
          <div class="flex items-center gap-3 p-3 rounded-xl bg-gradient-to-r from-info/10 to-info/10 border border-info/20">
            <div class="flex-1">
              <p class="text-sm font-semibold text-info">Stay on track</p>
              <p class="text-[10px] text-txt-muted mt-0.5">Get gentle reminders to keep your streak alive and hit your goals</p>
            </div>
            <div class="flex items-center gap-2">
              <button
                @click="notif.subscribe()"
                :disabled="notif.isLoading.value"
                class="px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-info hover:bg-info transition-all active:scale-95 disabled:opacity-50"
              >
                {{ notif.isLoading.value ? '...' : 'Enable' }}
              </button>
              <button
                @click="notif.dismissPrompt()"
                class="px-2 py-1.5 rounded-lg text-xs text-txt-muted hover:text-txt-secondary transition-colors"
              >
                Later
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Main dashboard grid — 3 columns on desktop, stacked on mobile -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">

      <!-- Mood Check-in (col 1) -->
      <div class="glass-card p-5 animate-fade-in flex flex-col">
        <div class="flex items-center gap-2 mb-4">
          <span class="text-sm font-semibold text-txt-primary">How are you feeling?</span>
        </div>

        <!-- Mood grid — 3 cols in this narrower card -->
        <div class="grid grid-cols-3 gap-2 mb-4" :class="dashMoodOnCooldown ? 'opacity-40 pointer-events-none' : ''">
          <button
            v-for="m in moods"
            :key="m.emoji"
            @click="logDashMood(m.emoji)"
            :disabled="dashMoodSubmitting"
            class="flex flex-col items-center gap-1.5 py-3 rounded-xl bg-surface-2/50 border border-bdr/50 hover:bg-surface-3 hover:border-bdr-hover transition-all active:scale-95"
            :title="m.label"
          >
            <component :is="moodIcons[m.emoji]" :size="22" class="text-accent" v-if="moodIcons[m.emoji]" />
            <Meh v-else :size="22" class="text-accent" />
            <span class="text-[10px] text-txt-muted">{{ m.label }}</span>
          </button>
        </div>

        <!-- Cooldown notice -->
        <div v-if="dashMoodOnCooldown" class="text-center">
          <p class="text-xs text-txt-muted">Next check-in in <span class="text-accent">{{ dashMoodTimeLeft }}</span></p>
        </div>

        <!-- Success / Error -->
        <p v-if="dashMoodSuccess" class="text-xs text-success text-center">{{ dashMoodSuccess }}</p>
        <p v-if="dashMoodError" class="text-xs text-red-400 text-center">{{ dashMoodError }}</p>

        <!-- Breathwork suggestion (acute intervention for negative moods) -->
        <div
          v-if="dashBreathworkSuggestion"
          class="mt-3 p-3 rounded-xl bg-info/8 border border-info/15 animate-fade-in relative overflow-hidden"
        >
          <div class="absolute top-0 left-0 bottom-0 w-[3px] bg-gradient-to-b from-info to-info" />
          <div class="pl-3">
            <p class="text-xs text-info font-medium mb-1.5">{{ dashBreathworkSuggestion }}</p>
            <div class="flex items-center gap-3">
              <a
                href="https://boxbreather.com"
                target="_blank"
                class="text-xs font-semibold text-info hover:text-info transition-colors"
              >Breathe now &rarr;</a>
              <button
                @click="dashBreathworkSuggestion = null"
                class="text-[10px] text-txt-muted hover:text-txt-secondary transition-colors"
              >Dismiss</button>
            </div>
          </div>
        </div>

        <!-- Recent moods sparkline — pushed to bottom -->
        <div class="flex-1" />
        <div v-if="dashboardData?.mood.has_data && dashboardData.mood.recent.length > 0" class="flex items-center gap-1.5 mt-3 pt-3 border-t border-bdr/50">
          <template v-for="(entry, i) in dashboardData.mood.recent.slice(0, 5)" :key="i">
            <div
              class="w-7 h-7 rounded-lg bg-surface-3 flex items-center justify-center transition-transform hover:scale-110"
              :title="entry.label + ' — ' + timeAgo(entry.date)"
            >
              <component :is="moodIcons[entry.emoji]" :size="14" class="text-accent" v-if="moodIcons[entry.emoji]" />
              <Meh v-else :size="14" class="text-accent" />
            </div>
          </template>
          <span class="text-[10px] text-txt-muted ml-1">recent</span>
        </div>
        <div v-if="dashboardData?.mood.has_data" class="text-[10px] text-txt-muted mt-2">{{ dashboardData.mood.total }} total logs</div>
      </div>

      <!-- Today's Challenges + Weekly Quests (col 2) -->
      <div class="flex flex-col gap-4">

      <!-- Daily Challenges -->
      <div v-if="gamificationData && gamificationData.daily_challenges.length > 0" class="glass-card p-5 animate-fade-in flex-1 flex flex-col">
        <div class="flex items-center gap-2 mb-4">
          <Target :size="14" class="text-accent" />
          <span class="text-sm font-semibold text-txt-primary">Today's Challenges</span>
          <span class="ml-auto text-xs text-txt-muted">
            {{ gamificationData.daily_challenges.filter(c => c.is_completed).length }}/{{ gamificationData.daily_challenges.length }}
          </span>
        </div>
        <div class="space-y-2 flex-1">
          <div
            v-for="challenge in gamificationData.daily_challenges"
            :key="challenge.challenge_key"
            class="flex items-center gap-3 py-2.5 px-3 rounded-xl transition-colors border"
            :class="challenge.is_completed ? 'bg-success/8 border-success/10' : 'bg-surface-2/50 border-bdr/50'"
          >
            <CheckCircle2
              v-if="challenge.is_completed"
              :size="16"
              class="flex-shrink-0 text-success"
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
              <p v-if="challenge.goal_connection" class="text-[9px] text-accent-alt leading-tight mt-0.5">Supports: {{ challenge.goal_connection }}</p>
            </div>
            <span
              class="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded leading-none"
              :class="challenge.is_completed ? 'bg-success/15 text-success' : 'bg-accent/15 text-accent'"
            >+{{ challenge.xp_reward }} XP</span>
          </div>
        </div>
      </div>

      <!-- Weekly Quests -->
      <div v-if="gamificationData && gamificationData.weekly_quests && gamificationData.weekly_quests.length > 0" class="glass-card p-5 animate-fade-in">
        <div class="flex items-center gap-2 mb-3">
          <Star :size="14" class="text-accent-alt" />
          <span class="text-sm font-semibold text-txt-primary">Weekly Quests</span>
          <span class="ml-auto text-xs text-txt-muted">
            {{ gamificationData.weekly_quests.filter(q => q.is_completed).length }}/{{ gamificationData.weekly_quests.length }}
          </span>
        </div>
        <div class="space-y-2">
          <div
            v-for="quest in gamificationData.weekly_quests"
            :key="quest.quest_key"
            class="flex items-center gap-3 py-2.5 px-3 rounded-xl transition-colors border"
            :class="quest.is_completed ? 'bg-accent-alt/8 border-accent-alt/10' : 'bg-surface-2/50 border-bdr/50'"
          >
            <CheckCircle2
              v-if="quest.is_completed"
              :size="16"
              class="flex-shrink-0 text-accent-alt"
            />
            <div
              v-else
              class="flex-shrink-0 w-4 h-4 rounded-full border-2 border-accent-alt/40"
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
              :class="quest.is_completed ? 'bg-accent-alt/15 text-accent-alt' : 'bg-accent-alt/15 text-accent-alt-bright'"
            >+{{ quest.xp_reward }} XP</span>
          </div>
        </div>
      </div>

      </div><!-- /challenges+quests column -->

      <!-- Week in Review (col 3) -->
      <div class="flex flex-col">
        <WeeklyNarrative :api="api" class="flex-1" />
      </div>

      </div><!-- /main 3-col grid -->

      <!-- Contextual Insight Cards (Deepstash-style micro-learning) -->
      <div v-if="insightCards.length > 0" class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <InsightCard
          v-for="card in insightCards"
          :key="card.key"
          :insight-key="card.key"
          :title="card.title"
          :content="card.content"
          :category="card.category"
          @dismiss="dismissInsight"
        />
      </div>

      <!-- Badges + XP Activity — single full-width card -->
      <div v-if="gamificationData" class="glass-card p-5 animate-fade-in mb-6">
        <div class="flex flex-col lg:flex-row lg:gap-6">
          <!-- Badge Showcase -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-4">
              <Trophy :size="14" class="text-accent" />
              <span class="text-sm font-semibold text-txt-primary">Badges</span>
              <span class="ml-auto text-xs text-txt-muted">
                {{ gamificationData.badges.filter(b => b.earned_at !== null).length }}/{{ ALL_BADGES.length }} earned
              </span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <div
                v-for="badge in ALL_BADGES"
                :key="badge.key"
                class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border transition-all"
                :class="gamificationData.badges.find(b => b.badge_key === badge.key && b.earned_at)
                  ? 'bg-accent/8 border-accent/20 hover:border-accent/40'
                  : 'bg-surface-2/40 border-bdr/30 opacity-40'"
                :title="badge.description"
              >
                <component
                  v-if="gamificationData.badges.find(b => b.badge_key === badge.key && b.earned_at) && (badgeIcons[badge.key] || (badge.key.startsWith('prestige_') && prestigeIcons[(parseInt(badge.key.split('_')[1]) - 1) % prestigeIcons.length]))"
                  :is="badgeIcons[badge.key] || prestigeIcons[(parseInt(badge.key.split('_')[1]) - 1) % prestigeIcons.length]"
                  :size="16"
                  :class="badge.key.startsWith('prestige_') ? 'text-accent-alt' : 'text-accent'"
                />
                <Lock v-else :size="14" class="text-txt-muted" />
                <span class="text-[10px] text-txt-muted whitespace-nowrap">{{ badge.title }}</span>
              </div>
            </div>
          </div>

          <!-- XP Activity Feed (sidebar on desktop, stacked on mobile) -->
          <div v-if="gamificationData.recent_xp.length > 0"
            class="lg:w-56 flex-shrink-0 mt-4 pt-4 border-t border-bdr/50 lg:mt-0 lg:pt-0 lg:border-t-0 lg:border-l lg:border-bdr/50 lg:pl-6">
            <div class="flex items-center gap-2 mb-3">
              <Star :size="14" class="text-accent" />
              <span class="text-sm font-semibold text-txt-primary">Recent XP</span>
            </div>
            <div class="space-y-2">
              <div
                v-for="(entry, i) in gamificationData.recent_xp.slice(0, 5)"
                :key="i"
                class="flex items-center gap-2 py-1 px-2 rounded-lg bg-surface-2/40"
              >
                <component
                  v-if="xpSourceIcons[entry.source]"
                  :is="xpSourceIcons[entry.source]"
                  :size="11"
                  class="flex-shrink-0 text-txt-muted"
                />
                <span class="text-[11px] font-semibold text-accent flex-shrink-0">+{{ entry.amount }}</span>
                <span class="text-[11px] text-txt-muted truncate">{{ stripEmoji(entry.description) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Analytics Dashboard (main visualization) -->
      <div class="mb-6">
        <AnalyticsDashboard />
      </div>

      <!-- Module Cards Grid -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">

        <!-- HABITS CARD -->
        <button
          @click="emit('navigate', 'habits')"
          class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
          style="animation-delay: 50ms"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-success/10 flex items-center justify-center">
                <TrendingUp :size="18" class="text-success" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Habits</span>
            </div>
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
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
                  :class="dashboardData.habits.completion_rate >= 0.8 ? 'bg-success' : dashboardData.habits.completion_rate >= 0.5 ? 'bg-accent' : 'bg-surface-4'"
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
          @click="emit('navigate', 'goals')"
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
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
          </div>
          <template v-if="dashboardData.goals.has_data">
            <div class="flex-1 flex flex-col">
              <div class="flex items-baseline gap-4 mb-3">
                <div>
                  <span class="text-2xl font-bold text-txt-primary">{{ dashboardData.goals.active }}</span>
                  <span class="text-xs text-txt-muted ml-1">active</span>
                </div>
                <div v-if="dashboardData.goals.completed > 0">
                  <span class="text-lg font-semibold text-success">{{ dashboardData.goals.completed }}</span>
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
          @click="emit('navigate', 'meditate')"
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
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
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
          @click="emit('navigate', 'journal')"
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
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
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
                <component :is="moodIcons[entry.emoji]" :size="14" class="text-accent" v-if="moodIcons[entry.emoji]" />
                <Meh v-else :size="14" class="text-accent" />
              </div>
            </template>
            <span class="text-xs text-txt-muted ml-1">recent moods</span>
          </div>
        </button>

        <!-- THERAPIST CARD -->
        <button
          @click="emit('navigate', 'therapist')"
          class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
          style="animation-delay: 250ms"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-teal-500/10 flex items-center justify-center">
                <MessageCircleHeart :size="18" class="text-teal-400" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Wellness Bot</span>
            </div>
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
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

        <!-- BREATHWORK CARD -->
        <a
          href="https://theboxbreather.com"
          target="_blank"
          rel="noopener noreferrer"
          class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
          style="animation-delay: 300ms"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-sky-500/10 flex items-center justify-center">
                <Wind :size="18" class="text-sky-400" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Breathwork</span>
            </div>
            <ChevronRight :size="16" class="text-txt-muted/40 group-hover:text-txt-muted transition-colors" />
          </div>
          <p class="text-sm text-txt-secondary mb-1">Box breathing exercises</p>
          <p class="text-xs text-txt-muted mt-auto">theboxbreather.com</p>
        </a>

      </div>

      <!-- ===== INSTALLED THEMES ===== -->
      <div v-if="installedThemes.length > 0" class="mt-6">
        <h3 class="text-sm font-semibold text-txt-secondary mb-3">My Themes</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            v-for="install in installedThemes"
            :key="install.id"
            class="theme-grid-item"
            :style="{
              gridColumn: `span ${Math.min(install.pos_w <= 6 ? 1 : 2, 2)}`,
              minHeight: `${install.pos_h * 60}px`,
            }"
          >
            <ThemeRenderer
              :theme="install.theme"
              studio="life"
              :show-title-bar="true"
              :removable="true"
              @remove="uninstallTheme(install.id)"
            />
          </div>
        </div>
      </div>

    </template>
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
  0%, 100% { box-shadow: 0 0 8px rgb(var(--accent-alt) / 0.1); }
  50% { box-shadow: 0 0 20px rgb(var(--accent-alt) / 0.25), 0 0 8px rgb(var(--accent) / 0.15); }
}

/* Skeleton loading placeholders */
.skeleton-pulse {
  background: linear-gradient(90deg, rgba(255 255 255 / 0.06) 25%, rgba(255 255 255 / 0.12) 50%, rgba(255 255 255 / 0.06) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Respect reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  .prestige-star,
  .multiplier-pulse,
  .prestige-bar-shimmer,
  .prestige-banner-glow,
  .skeleton-pulse {
    animation: none !important;
  }
}
</style>
