<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api, getToken } from '@core/api/client'
import {
  TrendingUp, TrendingDown, Minus, Activity, Brain, Flame, BarChart3,
  Zap, Clock, ArrowRight, Loader2, AlertCircle, ChevronDown, ChevronRight,
} from 'lucide-vue-next'

interface ForecastData {
  period_days: number
  total_entries: number
  trend: any
  day_of_week: any
  forecast: any
  habit_correlations: any
  habit_amount_correlations: any
  streak_correlations: any
  engagement_correlations: any
  lagged_correlations: any
  interaction_effects: any
  volatility: any
  meditation_effectiveness: any
  meditation_type_breakdown: any
}

const data = ref<ForecastData | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const expandedSections = ref<Set<string>>(new Set(['trend', 'habits', 'meditation']))

async function fetchAnalytics() {
  loading.value = true
  error.value = null
  try {
    data.value = await api.get<ForecastData>('/api/life/mood/forecast?days=30')
  } catch (e: any) {
    error.value = e.message || 'Failed to load analytics'
  } finally {
    loading.value = false
  }
}

onMounted(fetchAnalytics)

function toggleSection(key: string) {
  if (expandedSections.value.has(key)) {
    expandedSections.value.delete(key)
  } else {
    expandedSections.value.add(key)
  }
}

// Helpers
function valenceColor(val: number | null): string {
  if (val === null) return 'text-txt-muted'
  if (val >= 2) return 'text-emerald-400'
  if (val >= 0.5) return 'text-sky-400'
  if (val >= -0.5) return 'text-txt-secondary'
  if (val >= -2) return 'text-amber-400'
  return 'text-red-400'
}

function deltaColor(val: number): string {
  if (val > 0.3) return 'text-emerald-400'
  if (val > 0) return 'text-emerald-400/70'
  if (val > -0.3) return 'text-txt-muted'
  return 'text-red-400'
}

function barWidth(val: number, max: number): string {
  if (max === 0) return '0%'
  return Math.min(100, Math.max(2, (Math.abs(val) / max) * 100)) + '%'
}

const trendIcon = computed(() => {
  if (!data.value?.trend) return Minus
  const d = data.value.trend.direction
  if (d === 'improving' || d === 'slightly_improving') return TrendingUp
  if (d === 'declining' || d === 'slightly_declining') return TrendingDown
  return Minus
})

const trendColor = computed(() => {
  if (!data.value?.trend) return 'text-txt-muted'
  const d = data.value.trend.direction
  if (d === 'improving') return 'text-emerald-400'
  if (d === 'slightly_improving') return 'text-emerald-400/70'
  if (d === 'declining') return 'text-red-400'
  if (d === 'slightly_declining') return 'text-amber-400'
  return 'text-txt-secondary'
})
</script>

<template>
  <div class="space-y-4">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 :size="24" class="text-accent animate-spin" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="glass-card p-4 border-red-500/30">
      <div class="flex items-center gap-2 text-red-400">
        <AlertCircle :size="16" />
        <span class="text-sm">{{ error }}</span>
      </div>
    </div>

    <!-- No data -->
    <div v-else-if="!data || data.total_entries < 3" class="glass-card p-6 text-center">
      <Activity :size="32" class="mx-auto text-txt-muted mb-3" />
      <p class="text-sm text-txt-muted">Log a few moods and habits to unlock analytics.</p>
      <p class="text-xs text-txt-muted mt-1">Need at least 3 mood entries to start.</p>
    </div>

    <!-- Analytics -->
    <template v-else>
      <!-- Top row: Key metrics -->
      <div class="grid grid-cols-3 gap-3">
        <!-- Mood Trend -->
        <div class="glass-card p-4">
          <div class="flex items-center gap-2 mb-2">
            <component :is="trendIcon" :size="16" :class="trendColor" />
            <span class="text-xs text-txt-muted">Mood Trend</span>
          </div>
          <p class="text-lg font-bold" :class="trendColor">
            {{ data.trend.avg_valence >= 0 ? '+' : '' }}{{ data.trend.avg_valence }}
          </p>
          <p class="text-[10px] text-txt-muted mt-1">{{ data.trend.description }}</p>
        </div>

        <!-- Volatility -->
        <div class="glass-card p-4">
          <div class="flex items-center gap-2 mb-2">
            <Activity :size="16" class="text-violet-400" />
            <span class="text-xs text-txt-muted">Stability</span>
          </div>
          <p class="text-lg font-bold" :class="{
            'text-emerald-400': data.volatility.level === 'low',
            'text-amber-400': data.volatility.level === 'moderate',
            'text-red-400': data.volatility.level === 'high',
            'text-txt-muted': !data.volatility.current_volatility,
          }">
            {{ data.volatility.level || '--' }}
          </p>
          <p class="text-[10px] text-txt-muted mt-1">{{ data.volatility.description }}</p>
        </div>

        <!-- Forecast -->
        <div class="glass-card p-4">
          <div class="flex items-center gap-2 mb-2">
            <Brain :size="16" class="text-accent" />
            <span class="text-xs text-txt-muted">Tomorrow</span>
          </div>
          <p class="text-lg font-bold" :class="valenceColor(data.forecast.forecast_valence)">
            {{ data.forecast.forecast_label || '--' }}
          </p>
          <p class="text-[10px] text-txt-muted mt-1">
            {{ data.forecast.confidence }} confidence
          </p>
        </div>
      </div>

      <!-- Day of Week Pattern -->
      <div v-if="data.day_of_week.days?.length" class="glass-card p-4">
        <div class="flex items-center gap-2 mb-3">
          <Clock :size="14" class="text-accent" />
          <span class="text-xs font-medium text-txt-primary">Weekly Pattern</span>
          <span class="text-[10px] text-txt-muted ml-auto">{{ data.day_of_week.description }}</span>
        </div>
        <div class="flex gap-1 h-16 items-end">
          <div
            v-for="day in data.day_of_week.days"
            :key="day.day"
            class="flex-1 flex flex-col items-center gap-1"
          >
            <div
              class="w-full rounded-t transition-all"
              :class="day.avg_valence != null ? (day.avg_valence >= 1 ? 'bg-emerald-500/60' : day.avg_valence >= 0 ? 'bg-sky-500/40' : 'bg-amber-500/40') : 'bg-surface-3'"
              :style="{ height: day.avg_valence != null ? Math.max(4, ((day.avg_valence + 3) / 6) * 48) + 'px' : '4px' }"
            ></div>
            <span class="text-[9px] text-txt-muted">{{ day.day.slice(0, 2) }}</span>
          </div>
        </div>
      </div>

      <!-- Habit Correlations -->
      <div class="glass-card overflow-hidden">
        <button @click="toggleSection('habits')" class="w-full flex items-center gap-2 p-4 text-left hover:bg-surface-2/30 transition-colors">
          <Flame :size="14" class="text-emerald-400" />
          <span class="text-xs font-medium text-txt-primary flex-1">Habit Impact</span>
          <component :is="expandedSections.has('habits') ? ChevronDown : ChevronRight" :size="14" class="text-txt-muted" />
        </button>
        <div v-if="expandedSections.has('habits')" class="px-4 pb-4 space-y-3">
          <!-- Binary correlations -->
          <div v-if="data.habit_correlations.habits?.length">
            <p class="text-[10px] text-txt-muted mb-2 uppercase tracking-wide">Did / Didn't Do</p>
            <div v-for="h in data.habit_correlations.habits" :key="h.habit_name" class="flex items-center gap-2 mb-2">
              <span class="text-xs text-txt-secondary w-24 truncate">{{ h.habit_name }}</span>
              <div class="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden relative">
                <div
                  class="h-full rounded-full transition-all"
                  :class="h.delta > 0 ? 'bg-emerald-500/70' : 'bg-red-500/50'"
                  :style="{ width: barWidth(h.delta, 3) }"
                ></div>
              </div>
              <span class="text-xs font-mono w-12 text-right" :class="deltaColor(h.delta)">{{ h.delta > 0 ? '+' : '' }}{{ h.delta }}</span>
            </div>
          </div>

          <!-- Amount correlations -->
          <div v-if="data.habit_amount_correlations?.habits?.length">
            <p class="text-[10px] text-txt-muted mb-2 uppercase tracking-wide">Amount Impact (Pearson r)</p>
            <div v-for="h in data.habit_amount_correlations.habits" :key="h.habit_name" class="flex items-center gap-2 mb-2">
              <span class="text-xs text-txt-secondary w-24 truncate">{{ h.habit_name }}</span>
              <div class="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="h.r > 0 ? 'bg-sky-500/70' : 'bg-amber-500/50'"
                  :style="{ width: barWidth(h.r, 1) }"
                ></div>
              </div>
              <span class="text-xs font-mono w-16 text-right" :class="h.significant ? 'text-sky-400' : 'text-txt-muted'">
                r={{ h.r }}{{ h.significant ? '*' : '' }}
              </span>
            </div>
          </div>

          <!-- Streak correlations -->
          <div v-if="data.streak_correlations?.habits?.length">
            <p class="text-[10px] text-txt-muted mb-2 uppercase tracking-wide">Streak Effect</p>
            <div v-for="h in data.streak_correlations.habits" :key="h.habit_name" class="flex items-center gap-2 mb-2">
              <span class="text-xs text-txt-secondary w-24 truncate">{{ h.habit_name }}</span>
              <div class="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full bg-orange-500/60 transition-all"
                  :style="{ width: barWidth(h.r, 1) }"
                ></div>
              </div>
              <span class="text-xs font-mono w-16 text-right" :class="h.significant ? 'text-orange-400' : 'text-txt-muted'">
                r={{ h.r }}{{ h.significant ? '*' : '' }}
              </span>
            </div>
          </div>

          <p class="text-[10px] text-txt-muted italic">{{ data.habit_correlations.description }}</p>
          <p v-if="data.streak_correlations?.description" class="text-[10px] text-txt-muted italic">{{ data.streak_correlations.description }}</p>
        </div>
      </div>

      <!-- Meditation -->
      <div class="glass-card overflow-hidden">
        <button @click="toggleSection('meditation')" class="w-full flex items-center gap-2 p-4 text-left hover:bg-surface-2/30 transition-colors">
          <Brain :size="14" class="text-violet-400" />
          <span class="text-xs font-medium text-txt-primary flex-1">Meditation Analysis</span>
          <component :is="expandedSections.has('meditation') ? ChevronDown : ChevronRight" :size="14" class="text-txt-muted" />
        </button>
        <div v-if="expandedSections.has('meditation')" class="px-4 pb-4 space-y-3">
          <!-- Overall effectiveness -->
          <div v-if="data.meditation_effectiveness.avg_delta != null" class="flex items-center gap-3">
            <span class="text-xs text-txt-muted">Overall shift:</span>
            <span class="text-sm font-bold" :class="deltaColor(data.meditation_effectiveness.avg_delta)">
              {{ data.meditation_effectiveness.avg_delta > 0 ? '+' : '' }}{{ data.meditation_effectiveness.avg_delta }}
            </span>
            <span class="text-[10px] text-txt-muted">
              ({{ data.meditation_effectiveness.improved }}/{{ data.meditation_effectiveness.sessions_analyzed }} improved)
            </span>
          </div>

          <!-- By type -->
          <div v-if="data.meditation_type_breakdown?.by_type?.length">
            <p class="text-[10px] text-txt-muted mb-2 uppercase tracking-wide">By Type</p>
            <div v-for="t in data.meditation_type_breakdown.by_type" :key="t.name" class="flex items-center gap-2 mb-2">
              <span class="text-xs text-txt-secondary w-28 truncate capitalize">{{ t.name.replace('_', ' ') }}</span>
              <div class="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="t.avg_delta > 0 ? 'bg-violet-500/60' : 'bg-red-500/40'"
                  :style="{ width: barWidth(t.avg_delta, 3) }"
                ></div>
              </div>
              <span class="text-xs font-mono w-16 text-right" :class="deltaColor(t.avg_delta)">
                {{ t.avg_delta > 0 ? '+' : '' }}{{ t.avg_delta }}
              </span>
              <span class="text-[10px] text-txt-muted w-8">({{ t.sessions }})</span>
            </div>
          </div>

          <!-- By duration -->
          <div v-if="data.meditation_type_breakdown?.by_duration?.length">
            <p class="text-[10px] text-txt-muted mb-2 uppercase tracking-wide">By Duration</p>
            <div v-for="d in data.meditation_type_breakdown.by_duration" :key="d.name" class="flex items-center gap-2 mb-1.5">
              <span class="text-xs text-txt-secondary w-16">{{ d.name }} min</span>
              <div class="flex-1 h-2.5 bg-surface-3 rounded-full overflow-hidden">
                <div class="h-full rounded-full bg-violet-500/40 transition-all" :style="{ width: barWidth(d.avg_delta, 3) }"></div>
              </div>
              <span class="text-[10px] font-mono w-12 text-right" :class="deltaColor(d.avg_delta)">{{ d.avg_delta > 0 ? '+' : '' }}{{ d.avg_delta }}</span>
            </div>
          </div>

          <p class="text-[10px] text-txt-muted italic">{{ data.meditation_type_breakdown?.description || data.meditation_effectiveness.description }}</p>
        </div>
      </div>

      <!-- Engagement (Journal + Therapist) -->
      <div v-if="data.engagement_correlations" class="glass-card overflow-hidden">
        <button @click="toggleSection('engagement')" class="w-full flex items-center gap-2 p-4 text-left hover:bg-surface-2/30 transition-colors">
          <BarChart3 :size="14" class="text-sky-400" />
          <span class="text-xs font-medium text-txt-primary flex-1">Self-Reflection Impact</span>
          <component :is="expandedSections.has('engagement') ? ChevronDown : ChevronRight" :size="14" class="text-txt-muted" />
        </button>
        <div v-if="expandedSections.has('engagement')" class="px-4 pb-4 space-y-2">
          <div v-for="item in [data.engagement_correlations.journal, data.engagement_correlations.therapist, data.engagement_correlations.any_engagement].filter(Boolean)" :key="item.label" class="flex items-center gap-2">
            <span class="text-xs text-txt-secondary w-28 capitalize">{{ item.label }}</span>
            <div class="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="item.delta > 0 ? 'bg-sky-500/60' : 'bg-red-500/40'"
                :style="{ width: barWidth(item.delta, 3) }"
              ></div>
            </div>
            <span class="text-xs font-mono w-12 text-right" :class="deltaColor(item.delta)">{{ item.delta > 0 ? '+' : '' }}{{ item.delta }}</span>
            <span class="text-[10px] text-txt-muted w-12">{{ item.days_with }}d</span>
          </div>
          <p class="text-[10px] text-txt-muted italic">{{ data.engagement_correlations.description }}</p>
        </div>
      </div>

      <!-- Lagged Effects -->
      <div v-if="data.lagged_correlations?.factors?.length" class="glass-card overflow-hidden">
        <button @click="toggleSection('lagged')" class="w-full flex items-center gap-2 p-4 text-left hover:bg-surface-2/30 transition-colors">
          <ArrowRight :size="14" class="text-amber-400" />
          <span class="text-xs font-medium text-txt-primary flex-1">Delayed Effects (Today → Tomorrow)</span>
          <component :is="expandedSections.has('lagged') ? ChevronDown : ChevronRight" :size="14" class="text-txt-muted" />
        </button>
        <div v-if="expandedSections.has('lagged')" class="px-4 pb-4 space-y-2">
          <div v-for="f in data.lagged_correlations.factors" :key="f.name" class="mb-3">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs text-txt-secondary flex-1">{{ f.name }}</span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded"
                :class="{
                  'bg-amber-500/15 text-amber-400': f.effect_timing === 'delayed',
                  'bg-emerald-500/15 text-emerald-400': f.effect_timing === 'immediate',
                  'bg-sky-500/15 text-sky-400': f.effect_timing === 'both',
                }"
              >{{ f.effect_timing }}</span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-[10px]">
              <div class="flex items-center gap-1">
                <span class="text-txt-muted">Same day:</span>
                <span class="font-mono" :class="f.same_day.r != null ? deltaColor(f.same_day.r) : 'text-txt-muted'">
                  {{ f.same_day.r != null ? 'r=' + f.same_day.r : '--' }}
                </span>
              </div>
              <div class="flex items-center gap-1">
                <span class="text-txt-muted">Next day:</span>
                <span class="font-mono" :class="f.next_day.r != null ? deltaColor(f.next_day.r) : 'text-txt-muted'">
                  {{ f.next_day.r != null ? 'r=' + f.next_day.r : '--' }}
                </span>
              </div>
            </div>
          </div>
          <p class="text-[10px] text-txt-muted italic">{{ data.lagged_correlations.description }}</p>
        </div>
      </div>

      <!-- Interaction Effects -->
      <div v-if="data.interaction_effects?.pairs?.length" class="glass-card overflow-hidden">
        <button @click="toggleSection('interactions')" class="w-full flex items-center gap-2 p-4 text-left hover:bg-surface-2/30 transition-colors">
          <Zap :size="14" class="text-yellow-400" />
          <span class="text-xs font-medium text-txt-primary flex-1">Behavior Combos</span>
          <component :is="expandedSections.has('interactions') ? ChevronDown : ChevronRight" :size="14" class="text-txt-muted" />
        </button>
        <div v-if="expandedSections.has('interactions')" class="px-4 pb-4 space-y-3">
          <div v-for="p in data.interaction_effects.pairs" :key="p.behavior_a + p.behavior_b" class="text-xs">
            <div class="flex items-center gap-2 mb-1.5">
              <span class="text-txt-primary font-medium">{{ p.behavior_a }} + {{ p.behavior_b }}</span>
              <span
                v-if="p.synergistic"
                class="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400"
              >synergy</span>
            </div>
            <div class="grid grid-cols-4 gap-1 text-[10px]">
              <div class="bg-surface-2 rounded px-2 py-1.5 text-center">
                <p class="font-mono font-bold" :class="valenceColor(p.avg_mood_both)">{{ p.avg_mood_both > 0 ? '+' : '' }}{{ p.avg_mood_both }}</p>
                <p class="text-txt-muted">Both</p>
              </div>
              <div class="bg-surface-2 rounded px-2 py-1.5 text-center">
                <p class="font-mono" :class="valenceColor(p.avg_mood_a_only)">{{ p.avg_mood_a_only > 0 ? '+' : '' }}{{ p.avg_mood_a_only }}</p>
                <p class="text-txt-muted truncate">{{ p.behavior_a }}</p>
              </div>
              <div class="bg-surface-2 rounded px-2 py-1.5 text-center">
                <p class="font-mono" :class="valenceColor(p.avg_mood_b_only)">{{ p.avg_mood_b_only > 0 ? '+' : '' }}{{ p.avg_mood_b_only }}</p>
                <p class="text-txt-muted truncate">{{ p.behavior_b }}</p>
              </div>
              <div class="bg-surface-2 rounded px-2 py-1.5 text-center">
                <p class="font-mono" :class="valenceColor(p.avg_mood_neither)">{{ p.avg_mood_neither > 0 ? '+' : '' }}{{ p.avg_mood_neither }}</p>
                <p class="text-txt-muted">Neither</p>
              </div>
            </div>
            <p class="text-[10px] text-txt-muted mt-1">
              Interaction: <span class="font-mono" :class="p.interaction_effect > 0.2 ? 'text-yellow-400' : 'text-txt-muted'">{{ p.interaction_effect > 0 ? '+' : '' }}{{ p.interaction_effect }}</span>
              &middot; {{ p.days_both }}d both, {{ p.days_neither }}d neither
            </p>
          </div>
          <p class="text-[10px] text-txt-muted italic">{{ data.interaction_effects.description }}</p>
        </div>
      </div>

      <!-- Meta -->
      <p class="text-[10px] text-txt-muted text-center">
        {{ data.total_entries }} mood entries over {{ data.period_days }} days &middot; * = statistically significant (p&lt;0.05)
      </p>
    </template>
  </div>
</template>
