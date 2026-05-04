<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ApiError } from '@core/api/client'
import {
  Settings, Brain as BrainIcon, CalendarDays, TrendingUp, BookOpen,
  MessageCircleHeart, Wind, Meh, Target,
} from 'lucide-vue-next'
import { moodIcons, getIcon } from '../icons'
import { playZugabotJingle } from '../composables/useCelebrationSounds'
import AnalyticsDashboard from '../AnalyticsDashboard.vue'
import InsightCard from '../components/InsightCard.vue'
import WeeklyNarrative from '../components/WeeklyNarrative.vue'
import ThemeRenderer from '../components/themes/ThemeRenderer.vue'
import { applyPreset } from '../theme-presets'
import { useLifeShared } from '../composables/useLifeShared'
import { useNotifications } from '../composables/useNotifications'

// ── Props & Emits ───────────────────────────────────────────────
const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const emit = defineEmits<{
  (e: 'navigate', tab: string): void
  (e: 'open-settings'): void
}>()

// ── Shared composable ───────────────────────────────────────────
const {
  moods,
  activePresetId,
  timeAgo,
  formatDashboardDate,
  formatDeadline,
  celebration,
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
  id: number
  theme_id: number
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

interface ForgeInstall {
  id: number
  creation_id: number
  studio: string
  pos_x: number
  pos_y: number
  pos_w: number
  pos_h: number
  enabled: boolean
}

interface ForgeCreationDetail {
  id: number
  name: string
  type: string
  source_html: string | null
  source_css: string | null
  source_js: string | null
  permissions: string | null
}

const installedThemes = ref<InstalledTheme[]>([])

async function fetchInstalledThemes() {
  try {
    const installs = await api.get<ForgeInstall[]>('/api/forge/installs?studio=life')
    const enabled = installs.filter(i => i.enabled)
    const creations = await Promise.all(
      enabled.map(i => api.get<ForgeCreationDetail>(`/api/forge/creations/${i.creation_id}`))
    )
    installedThemes.value = enabled
      .map((inst, idx): InstalledTheme | null => {
        const c = creations[idx]
        if (c.type !== 'widget') return null
        return {
          id: inst.id,
          theme_id: inst.creation_id,
          studio: inst.studio,
          pos_x: inst.pos_x,
          pos_y: inst.pos_y,
          pos_w: inst.pos_w,
          pos_h: inst.pos_h,
          enabled: inst.enabled,
          theme: {
            id: String(c.id),
            title: c.name,
            html: c.source_html || '',
            css: c.source_css,
            js: c.source_js || '',
            permissions: c.permissions ? JSON.parse(c.permissions) : [],
          },
        }
      })
      .filter((t): t is InstalledTheme => t !== null)
  } catch {
    // Themes are non-critical — don't block dashboard
  }
}

async function uninstallTheme(installId: number) {
  try {
    await api.delete(`/api/forge/installs/${installId}`)
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

// Gamification (prestige, share card) removed 2026-04-26 — moves to ZugaTokens layer.

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
    const res = await api.post<{ entry: { emoji: string; label: string }; streak: number; today_count: number; suggestion: { type: string; message: string } | null }>('/api/life/mood', {
      emoji,
      note: dashMoodNote.value.trim() || null,
    })
    dashMoodNote.value = ''
    if (res.suggestion?.type === 'breathwork') {
      dashBreathworkSuggestion.value = res.suggestion.message
    } else {
      dashBreathworkSuggestion.value = null
    }
    // Cooldown — UI shows the timer instead of duplicate success text
    dashMoodCooldownUntil.value = new Date(Date.now() + 6 * 3600000).toISOString()
    // Confirmation modal — domain milestone, replaces the old XP toast.
    // Streak-aware copy: longer streaks get stronger identity language.
    const streakDays = res.streak ?? 0
    const description = streakDays >= 7
      ? `${streakDays} days of showing up for yourself`
      : streakDays >= 3
      ? `${streakDays} days in a row — this is becoming who you are`
      : 'You paused to notice how you feel'
    celebration.activeBadge.value = {
      badge_key: 'first_mood',
      title: res.entry.label,
      description,
    }
    if (celebration.soundEnabled.value) playZugabotJingle()
    // Refresh dashboard in background — UI is already responsive
    void fetchDashboard()
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
    fetchInstalledThemes(),
    fetchInsightCards(),
    applyCustomColors(),
  ])

  // Theme installed event still re-fetches installed themes.
  window.addEventListener('zugatheme:installed', () => {
    fetchInstalledThemes()
  })
})
</script>

<template>
  <div>
    <!-- Share card removed 2026-04-26 (depended on gamification data). -->

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
      <!-- ============================================================
           HERO — editorial-weight greeting, eyebrow date, settings gear
           ============================================================ -->
      <header v-if="!props.embedded" class="flex items-start justify-between mb-10 md:mb-12 animate-fade-in">
        <div>
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent mb-2">
            {{ formatDashboardDate(dashboardData.date) }}
          </p>
          <h1 class="text-3xl md:text-5xl font-semibold tracking-tight text-txt-primary leading-[1.1]">
            {{ dashboardData.greeting }}
          </h1>
          <p class="text-sm md:text-base text-txt-secondary mt-3">
            Here's where you are.
          </p>
        </div>
        <button
          @click="emit('open-settings')"
          class="p-2.5 rounded-xl bg-surface-1/60 border border-bdr text-txt-secondary transition-all hover:text-txt-primary hover:bg-surface-2 hover:border-bdr-hover active:scale-95"
          title="Settings"
          aria-label="Settings"
        >
          <Settings :size="18" />
        </button>
      </header>
      <div v-else class="mb-6 md:mb-8"></div>

      <!-- ============================================================
           BENTO ROW 1 — This Week (col-span 7) + Habits hero (col-span 5)
           ============================================================ -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6 mb-4 md:mb-6">

      <!-- THIS WEEK (col-span 7) — narrative + last 7 mood logs sparkline -->
      <section class="lg:col-span-7 glass-card p-6 md:p-8 animate-fade-in flex flex-col">
        <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-txt-muted mb-4">This week</p>
        <WeeklyNarrative :api="api" class="flex-1" />
        <div
          v-if="dashboardData?.mood.has_data && dashboardData.mood.recent.length > 0"
          class="flex items-center gap-2 mt-6 pt-5 border-t border-bdr/50"
        >
          <template v-for="(entry, i) in dashboardData.mood.recent.slice(0, 7).slice().reverse()" :key="i">
            <div
              class="w-9 h-9 rounded-lg bg-surface-2/70 border border-bdr/40 flex items-center justify-center transition-all hover:scale-110 hover:border-accent/40"
              :title="entry.label + ' — ' + timeAgo(entry.date)"
            >
              <component :is="moodIcons[entry.emoji]" :size="16" class="text-accent" v-if="moodIcons[entry.emoji]" />
              <Meh v-else :size="16" class="text-accent" />
            </div>
          </template>
          <span class="text-[10px] font-semibold uppercase tracking-wider text-txt-muted ml-2">last 7 logs</span>
          <span class="ml-auto text-xs text-txt-muted tabular-nums">{{ dashboardData.mood.total }} total</span>
        </div>
      </section>

      <!-- HABITS HERO (col-span 5) — SVG ring + display-weight number -->
      <button
        @click="emit('navigate', 'habits')"
        class="lg:col-span-5 dash-card glass-card p-6 md:p-8 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col min-h-[300px]"
        style="animation-delay: 50ms"
      >
        <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-txt-muted">Habits · this week</p>

        <template v-if="dashboardData.habits.has_data">
          <div class="relative flex items-center justify-center my-auto py-4">
            <svg viewBox="0 0 120 120" class="w-44 h-44 -rotate-90" aria-hidden="true">
              <circle cx="60" cy="60" r="52" stroke="rgb(var(--surface-3))" stroke-width="6" fill="none" />
              <circle
                cx="60" cy="60" r="52"
                stroke="rgb(var(--accent))"
                stroke-width="6"
                fill="none"
                stroke-linecap="round"
                stroke-dasharray="326.7"
                :stroke-dashoffset="326.7 * (1 - dashboardData.habits.completion_rate)"
                class="transition-all duration-1000 ease-out drop-shadow-[0_0_8px_rgb(var(--accent)/0.35)]"
              />
            </svg>
            <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span class="text-6xl md:text-7xl font-semibold tracking-tighter text-txt-primary tabular-nums leading-none">
                {{ Math.round(dashboardData.habits.completion_rate * 100) }}<span class="text-3xl md:text-4xl text-txt-muted">%</span>
              </span>
              <span class="text-[11px] font-semibold uppercase tracking-wider text-txt-muted mt-2">
                {{ dashboardData.habits.completed }}/{{ dashboardData.habits.total_possible }} done
              </span>
            </div>
          </div>
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
          <div class="flex-1 flex flex-col items-center justify-center gap-3 my-8">
            <span class="text-6xl md:text-7xl font-semibold tracking-tighter text-txt-muted/40 leading-none">—</span>
            <p class="text-sm text-txt-secondary mt-3">Build consistent routines</p>
            <p class="text-xs text-txt-muted">Set up your first habits →</p>
          </div>
        </template>
      </button>

      </div><!-- /bento row 1 -->

      <!-- ============================================================
           BENTO ROW 2 — Mood pulse (col-span 5) + Goals (col-span 7)
           ============================================================ -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 md:gap-6 mb-4 md:mb-6">

      <!-- MOOD PULSE (col-span 5) — bigger touch areas, lime hover/active -->
      <section class="lg:col-span-5 glass-card p-6 md:p-8 animate-fade-in flex flex-col">
        <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-txt-muted mb-2">Today's pulse</p>
        <h2 class="text-xl md:text-2xl font-semibold tracking-tight text-txt-primary mb-5">
          How are you feeling?
        </h2>

        <div
          class="grid grid-cols-3 gap-2.5"
          :class="dashMoodOnCooldown ? 'opacity-40 pointer-events-none' : ''"
        >
          <button
            v-for="m in moods"
            :key="m.emoji"
            @click="logDashMood(m.emoji)"
            :disabled="dashMoodSubmitting"
            class="flex flex-col items-center gap-2 py-4 rounded-xl bg-surface-2/50 border border-bdr/50 transition-all active:scale-95 hover:bg-accent/10 hover:border-accent/50 hover:-translate-y-0.5"
            :aria-label="m.label"
          >
            <component :is="moodIcons[m.emoji]" :size="26" class="text-accent" v-if="moodIcons[m.emoji]" />
            <Meh v-else :size="26" class="text-accent" />
            <span class="text-[11px] font-medium text-txt-secondary">{{ m.label }}</span>
          </button>
        </div>

        <div v-if="dashMoodOnCooldown" class="text-center mt-4">
          <p class="text-xs text-txt-muted">Next check-in in <span class="text-accent font-semibold">{{ dashMoodTimeLeft }}</span></p>
        </div>

        <p v-if="dashMoodSuccess" class="text-xs text-success text-center mt-3">{{ dashMoodSuccess }}</p>
        <p v-if="dashMoodError" class="text-xs text-red-400 text-center mt-3">{{ dashMoodError }}</p>

        <div
          v-if="dashBreathworkSuggestion"
          class="mt-4 p-3 rounded-xl bg-info/8 border border-info/15 animate-fade-in relative overflow-hidden"
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
      </section>

      <!-- GOALS (col-span 7) — display-weight number + milestone bar -->
      <button
        @click="emit('navigate', 'goals')"
        class="lg:col-span-7 dash-card glass-card p-6 md:p-8 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
        style="animation-delay: 100ms"
      >
        <div class="flex items-center justify-between mb-4">
          <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-txt-muted">Goals</p>
          <Target :size="16" class="text-txt-muted group-hover:text-accent transition-colors" />
        </div>

        <template v-if="dashboardData.goals.has_data">
          <div class="flex items-baseline gap-3 mb-2">
            <span class="text-5xl md:text-6xl font-semibold tracking-tighter text-txt-primary tabular-nums leading-none">
              {{ dashboardData.goals.active }}
            </span>
            <span class="text-sm text-txt-secondary">active</span>
            <span v-if="dashboardData.goals.completed > 0" class="text-sm ml-2">
              <span class="text-success font-semibold tabular-nums">{{ dashboardData.goals.completed }}</span>
              <span class="text-txt-muted ml-1">done</span>
            </span>
          </div>

          <div v-if="dashboardData.goals.milestones_total > 0" class="mt-5">
            <div class="flex items-center justify-between text-xs text-txt-secondary mb-2">
              <span class="font-medium uppercase tracking-wider text-[10px] text-txt-muted">Milestones</span>
              <span class="tabular-nums">{{ dashboardData.goals.milestones_done }} / {{ dashboardData.goals.milestones_total }}</span>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-1.5 overflow-hidden">
              <div
                class="h-1.5 rounded-full bg-accent transition-all duration-700 ease-out"
                :style="{ width: Math.round((dashboardData.goals.milestones_done / dashboardData.goals.milestones_total) * 100) + '%' }"
              ></div>
            </div>
          </div>

          <div v-if="dashboardData.goals.nearest_deadline" class="flex items-center gap-2 text-xs text-txt-secondary mt-auto pt-5">
            <CalendarDays :size="13" class="text-accent" />
            <span class="font-medium text-txt-primary truncate">{{ dashboardData.goals.nearest_deadline.title }}</span>
            <span class="text-txt-muted">·</span>
            <span>{{ formatDeadline(dashboardData.goals.nearest_deadline.date) }}</span>
          </div>
        </template>
        <template v-else>
          <div class="flex-1 flex flex-col justify-center">
            <span class="text-5xl md:text-6xl font-semibold tracking-tighter text-txt-muted/40 mb-3 leading-none">—</span>
            <p class="text-sm text-txt-secondary mb-2">Set meaningful goals</p>
            <p class="text-xs text-txt-muted mb-4">Choose from templates or create your own</p>
            <div class="flex flex-wrap gap-1.5">
              <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Fitness</span>
              <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Learning</span>
              <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-md bg-surface-3 text-txt-muted">Career</span>
            </div>
          </div>
        </template>
      </button>

      </div><!-- /bento row 2 -->

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

      <!-- Badges + Recent XP card removed 2026-04-26 (gamification migration). -->

      <!-- ============================================================
           MODULE RAIL — compact secondary tier (different visual register
           than the bento glass-cards: lighter surface, smaller padding,
           hover lift). 4 shortcuts for tabs not already promoted in bento.
           ============================================================ -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">

        <!-- MEDITATE -->
        <button
          @click="emit('navigate', 'meditate')"
          class="group flex flex-col items-start gap-2 p-4 rounded-xl bg-surface-1/40 border border-bdr/30 transition-all hover:border-accent/40 hover:bg-surface-2/60 hover:-translate-y-0.5 active:translate-y-0"
        >
          <div class="flex items-center gap-2 w-full">
            <BrainIcon :size="14" class="text-txt-muted group-hover:text-accent transition-colors" />
            <span class="text-[11px] font-semibold uppercase tracking-wider text-txt-muted">Meditate</span>
          </div>
          <div v-if="dashboardData.meditation.has_data && dashboardData.meditation.sessions_this_week > 0" class="flex items-baseline gap-1">
            <span class="text-2xl font-semibold tabular-nums text-txt-primary leading-none">{{ dashboardData.meditation.sessions_this_week }}</span>
            <span class="text-xs text-txt-muted">this week</span>
          </div>
          <span v-else class="text-xs text-txt-secondary">Guided sessions →</span>
        </button>

        <!-- JOURNAL -->
        <button
          @click="emit('navigate', 'journal')"
          class="group flex flex-col items-start gap-2 p-4 rounded-xl bg-surface-1/40 border border-bdr/30 transition-all hover:border-accent/40 hover:bg-surface-2/60 hover:-translate-y-0.5 active:translate-y-0"
        >
          <div class="flex items-center gap-2 w-full">
            <BookOpen :size="14" class="text-txt-muted group-hover:text-accent transition-colors" />
            <span class="text-[11px] font-semibold uppercase tracking-wider text-txt-muted">Journal</span>
          </div>
          <div v-if="dashboardData.journal.has_data" class="flex items-baseline gap-1">
            <span class="text-2xl font-semibold tabular-nums text-txt-primary leading-none">{{ dashboardData.journal.entries_this_week }}</span>
            <span class="text-xs text-txt-muted">entries</span>
          </div>
          <span v-else class="text-xs text-txt-secondary">Write to reflect →</span>
        </button>

        <!-- COMPANION (Wellness Bot / Therapist) -->
        <button
          @click="emit('navigate', 'therapist')"
          class="group flex flex-col items-start gap-2 p-4 rounded-xl bg-surface-1/40 border border-bdr/30 transition-all hover:border-accent/40 hover:bg-surface-2/60 hover:-translate-y-0.5 active:translate-y-0"
        >
          <div class="flex items-center gap-2 w-full">
            <MessageCircleHeart :size="14" class="text-txt-muted group-hover:text-accent transition-colors" />
            <span class="text-[11px] font-semibold uppercase tracking-wider text-txt-muted">Companion</span>
          </div>
          <div v-if="dashboardData.therapist.has_data" class="flex items-baseline gap-1">
            <span class="text-2xl font-semibold tabular-nums text-txt-primary leading-none">{{ dashboardData.therapist.total_sessions }}</span>
            <span class="text-xs text-txt-muted">{{ dashboardData.therapist.total_sessions === 1 ? 'session' : 'sessions' }}</span>
          </div>
          <span v-else class="text-xs text-txt-secondary">Talk it through →</span>
        </button>

        <!-- BREATHWORK (external) -->
        <a
          href="https://theboxbreather.com"
          target="_blank"
          rel="noopener noreferrer"
          class="group flex flex-col items-start gap-2 p-4 rounded-xl bg-surface-1/40 border border-bdr/30 transition-all hover:border-accent/40 hover:bg-surface-2/60 hover:-translate-y-0.5 active:translate-y-0"
        >
          <div class="flex items-center gap-2 w-full">
            <Wind :size="14" class="text-txt-muted group-hover:text-accent transition-colors" />
            <span class="text-[11px] font-semibold uppercase tracking-wider text-txt-muted">Breathwork</span>
          </div>
          <span class="text-xs text-txt-secondary">Box breathing →</span>
        </a>

      </div>

      <!-- ===== ANALYTICS (kept, secondary tier — power-user dive) ===== -->
      <div class="mb-6">
        <AnalyticsDashboard />
      </div>

      <!-- Module Cards Grid (LEGACY — replaced by bento + module rail above; kept hidden as a safety net during rollout) -->
      <div v-if="false" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">

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
          class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
          style="animation-delay: 150ms"
        >
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center">
                <BrainIcon :size="18" class="text-violet-400" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Meditation</span>
            </div>
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
          class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group flex flex-col"
          style="animation-delay: 200ms"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-rose-500/10 flex items-center justify-center">
                <BookOpen :size="18" class="text-rose-400" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Journal & Mood</span>
            </div>
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
          </div>
          <template v-if="dashboardData.therapist.has_data">
            <p class="text-sm text-txt-secondary mb-2 line-clamp-1">{{ dashboardData.therapist.last_themes }}</p>
            <!-- Mood snapshot now renders as a full-width clamped block instead
                 of an inline pill — the field grew from a short label into
                 multi-paragraph narrative summaries, which broke the metadata
                 flex row (squished session count + timeAgo to a vertical
                 stack on the right). -->
            <p
              v-if="dashboardData.therapist.last_mood"
              class="text-xs text-teal-400/90 leading-relaxed mb-3 px-3 py-2 rounded-lg bg-teal-500/10 border border-teal-500/20 line-clamp-3"
            >
              {{ dashboardData.therapist.last_mood }}
            </p>
            <div class="flex items-center gap-2 text-xs text-txt-muted mt-auto">
              <span>{{ dashboardData.therapist.total_sessions }} {{ dashboardData.therapist.total_sessions === 1 ? 'session' : 'sessions' }}</span>
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
