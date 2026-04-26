<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ApiError } from '@core/api/client'
import { habitIcons, habitIconPicker, habitIconCategories, getIcon } from '../icons'
import { ChevronDown, ChevronUp, CircleDot } from 'lucide-vue-next'
import { useLifeShared } from '../composables/useLifeShared'

const emit = defineEmits<{
  (e: 'success'): void
}>()

const {
  gamificationData,
  withCelebration,
  fetchGamification,
  notifyTokenSpend,
  handleInsufficientTokens,
  handleServiceError,
  celebration,
  parseUTC,
} = useLifeShared()

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
  trigger: string | null
  created_at: string
  // Tiny Habits escalation
  full_target: number | null
  can_escalate: boolean
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


type HabitView = 'checkin' | 'history' | 'manage'
const habitView = ref<HabitView>('checkin')

const habitCheckin = ref<DailyCheckInResponse | null>(null)
const habitStreaks = ref<AllStreaksResponse | null>(null)
const habitHistory = ref<HabitHistoryResponse | null>(null)
const allHabits = ref<HabitDefinition[]>([])
const loadingHabits = ref(true)
const habitError = ref<string | null>(null)
const habitSuccess = ref<string | null>(null)
const habitSubmitting = ref(false)

// AI habit insight
const habitInsightLoading = ref(false)
const habitInsightText = ref<string | null>(null)
const historyDays = ref(7)

// New custom habit form
const newHabitName = ref('')
const newHabitIcon = ref('')  // Stores a Lucide icon name (e.g. 'dumbbell')
const newHabitUnit = ref('')
const newHabitTarget = ref<number | null>(null)
const newHabitTrigger = ref('')
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


async function toggleHabit(item: HabitCheckInItem) {
  habitError.value = null
  // Optimistic flip — UI feels instant. Revert if the API call fails.
  const wasLogged = item.logged
  item.logged = !wasLogged
  if (habitCheckin.value) {
    habitCheckin.value.completed_count += wasLogged ? -1 : 1
  }
  try {
    if (wasLogged) {
      const serverDate = habitCheckin.value?.date
      if (!serverDate) throw new Error('no_server_date')
      await api.delete(`/api/life/habits/log/${item.habit.id}/${serverDate}`)
    } else {
      const amt = amountInputs.value[item.habit.id]
      await api.post('/api/life/habits/log', {
        habit_id: item.habit.id,
        completed: true,
        amount: amt ? parseFloat(amt) : null,
      })
    }
    // Background reconciliation — streaks/counts may have shifted server-side.
    void fetchHabitCheckin()
    void fetchHabitStreaks()
  } catch (e) {
    // Revert optimistic update so the UI reflects truth.
    item.logged = wasLogged
    if (habitCheckin.value) {
      habitCheckin.value.completed_count += wasLogged ? 1 : -1
    }
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

// On focus, select all text so the cursor lands consistently at "end"
// (as it does after ↑/↓ steps). Typing replaces; arrow keys still step.
// Chrome refuses setSelectionRange on type=number, so .select() is the
// portable fallback that gives the same UX result.
function handleAmountFocus(e: FocusEvent) {
  const el = e.target as HTMLInputElement
  // Defer — focus event fires before browser places caret.
  requestAnimationFrame(() => { try { el.select() } catch { /* noop */ } })
}

// When the user presses ↑/↓ on an EMPTY amount input, seed it with the
// habit's default target so the next step lands somewhere meaningful
// instead of 0/1. Native step continues normally once a value exists.
function handleAmountKeydown(item: HabitCheckInItem, e: KeyboardEvent) {
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
  const current = amountInputs.value[item.habit.id]
  if (current) return  // existing value — let native step take over
  const target = item.habit.default_target
  if (target == null) return
  e.preventDefault()
  const seeded = e.key === 'ArrowUp'
    ? Number(target) + 1
    : Math.max(0, Number(target) - 1)
  amountInputs.value[item.habit.id] = String(seeded)
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
      trigger: newHabitTrigger.value.trim() || null,
    })
    newHabitName.value = ''
    newHabitIcon.value = ''
    newHabitUnit.value = ''
    newHabitTarget.value = null
    newHabitTrigger.value = ''
    showNewHabitForm.value = false
    habitSuccess.value = 'Habit created!'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
    emit('success')
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

async function escalateHabit(habitId: number) {
  try {
    await api.post(`/api/life/habits/${habitId}/escalate`)
    celebration.pushToast({ type: 'info', message: 'Target raised — you\'re ready for more', duration: 3000 })
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? 'Escalation failed'
    }
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
    emit('success')
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

async function fetchHabitInsight() {
  if (habitInsightLoading.value) return
  habitInsightLoading.value = true
  habitInsightText.value = null
  try {
    const res = await api.post<{ content: string; cost: number }>('/api/life/habits/insight')
    habitInsightText.value = res.content
    notifyTokenSpend()
  } catch (e) {
    if (e instanceof ApiError && e.status === 402) {
      habitError.value = handleInsufficientTokens('Habit Insights')
    } else if (e instanceof ApiError && e.status === 429) {
      habitError.value = handleServiceError('Insight Cooldown', (e.body as Record<string, string>).detail ?? 'Insights are available once per week. Check back later!')
    } else if (e instanceof ApiError && e.status === 400) {
      // Sparse-data gate — show the backend's user-friendly message directly.
      habitError.value = handleServiceError('Not Enough Data', (e.body as Record<string, string>).detail ?? 'Log a few more habits and moods, then try again.')
    } else if (e instanceof ApiError && e.status >= 500) {
      habitError.value = handleServiceError('Service Unavailable', 'The AI service is temporarily down. Your tokens were not charged. Please try again in a few minutes.')
    } else {
      habitError.value = handleServiceError('Generation Failed', 'Could not generate your habit insight right now. Please try again.')
    }
  } finally {
    habitInsightLoading.value = false
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

onMounted(async () => {
  loadingHabits.value = true
  await Promise.all([fetchHabitCheckin(), fetchHabitStreaks(), fetchAllHabits()])
  loadingHabits.value = false
})
</script>

<template>
  <!-- Sub-nav -->
  <div class="flex gap-3 mb-6">
    <button
      v-for="view in [
        { key: 'checkin', label: 'Check-in' },
        { key: 'history', label: 'History' },
        { key: 'manage', label: 'Manage' },
      ] as { key: HabitView; label: string }[]"
      :key="view.key"
      @click="habitView = view.key; if (view.key === 'history') fetchHabitHistory()"
      class="px-4 py-2.5 text-xs font-medium rounded-lg transition-colors"
      :class="habitView === view.key ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
    >
      {{ view.label }}
    </button>
  </div>

  <p v-if="habitError" class="text-sm text-red-400 mb-4">{{ habitError }}</p>

  <!-- ===== CHECK-IN VIEW ===== -->
  <template v-if="habitView === 'checkin'">
    <!-- Skeleton — shape-matched so cards don't shift when data arrives. -->
    <div v-if="loadingHabits && !habitCheckin" class="animate-fade-in">
      <div class="glass-card p-4 mb-6">
        <div class="flex items-center justify-between mb-2">
          <div class="bg-surface-3 animate-pulse h-3 w-40 rounded"></div>
          <div class="bg-surface-3 animate-pulse h-3 w-10 rounded"></div>
        </div>
        <div class="bg-surface-3 animate-pulse w-full h-2.5 rounded-full"></div>
      </div>
      <div class="space-y-2">
        <div v-for="i in 3" :key="i" class="glass-card px-4 py-3 flex items-center gap-3">
          <div class="bg-surface-3 animate-pulse w-6 h-6 rounded-md flex-shrink-0"></div>
          <div class="bg-surface-3 animate-pulse w-7 h-7 rounded-lg flex-shrink-0"></div>
          <div class="flex-1 flex flex-col gap-1.5">
            <div class="bg-surface-3 animate-pulse h-3 w-32 rounded"></div>
            <div class="bg-surface-3 animate-pulse h-2 w-20 rounded"></div>
          </div>
        </div>
      </div>
    </div>
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
            class="h-2.5 rounded-full transition-[width,background-color] duration-300 ease-out"
            :class="completionPercent === 100 ? 'bg-success' : 'bg-accent'"
            :style="{ width: completionPercent + '%' }"
          />
        </div>
      </div>

      <!-- Habit cards -->
      <div class="space-y-2">
        <div
          v-for="item in habitCheckin.habits"
          :key="item.habit.id"
          class="glass-card px-4 py-3 flex items-center gap-3 transition-shadow duration-150 ease-out"
          :class="item.logged ? 'ring-1 ring-success/30' : ''"
        >
          <button
            @click="toggleHabit(item)"
            class="w-6 h-6 rounded-md border-2 flex items-center justify-center transition-colors duration-100 ease-out flex-shrink-0"
            :class="item.logged
              ? 'bg-success border-success text-white'
              : 'border-bdr hover:border-accent'"
          >
            <span v-if="item.logged" class="text-xs">&#10003;</span>
          </button>
          <component :is="getIcon(item.habit.emoji)" :size="22" class="flex-shrink-0 text-accent" v-if="getIcon(item.habit.emoji)" />
          <CircleDot v-else :size="22" class="flex-shrink-0 text-accent" />
          <div class="flex-1 min-w-0">
            <span class="text-sm font-medium text-txt-primary">{{ item.habit.name }}</span>
            <p v-if="item.habit.trigger" class="text-[11px] text-txt-muted leading-tight mt-0.5">After {{ item.habit.trigger }}</p>
          </div>
          <div v-if="item.habit.unit" class="flex items-center gap-1.5">
            <input
              type="number"
              :value="amountInputs[item.habit.id] ?? ''"
              @input="amountInputs[item.habit.id] = ($event.target as HTMLInputElement).value"
              @focus="handleAmountFocus($event)"
              @keydown="handleAmountKeydown(item, $event)"
              @blur="updateHabitAmount(item)"
              @keyup.enter="updateHabitAmount(item)"
              :placeholder="item.habit.default_target ? String(item.habit.default_target) : '0'"
              class="w-14 px-1.5 py-1 text-sm text-center rounded-md bg-surface-3 text-txt-primary border border-bdr focus:border-accent focus:outline-none"
            />
            <span class="text-xs text-txt-muted w-12">{{ item.habit.unit }}</span>
          </div>
          <!-- Tiny Habits escalation button -->
          <button
            v-if="item.habit.can_escalate && item.logged"
            @click="escalateHabit(item.habit.id)"
            class="text-[10px] text-success hover:text-success transition-colors whitespace-nowrap"
            :title="`Level up to ${item.habit.full_target} ${item.habit.unit || ''}`"
          >
            Ready for more
          </button>
        </div>
      </div>

      <!-- AI Insight -->
      <div class="mt-6 glass-card p-4">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-txt-secondary">Weekly AI Insight</span>
          <button
            @click="fetchHabitInsight"
            :disabled="habitInsightLoading"
            class="text-xs text-accent-alt hover:text-accent-alt-bright transition-colors disabled:opacity-50"
          >
            {{ habitInsightLoading ? 'Analyzing...' : 'Generate Insight' }}
          </button>
        </div>
        <div v-if="habitInsightText" class="mt-3 p-3 rounded-lg bg-accent-alt/10 border border-accent-alt/20 animate-fade-in">
          <p class="text-xs text-txt-secondary leading-relaxed whitespace-pre-line">{{ habitInsightText }}</p>
        </div>
      </div>

      <!-- Reset options -->
      <div class="mt-4 flex flex-wrap gap-2">
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
          class="px-4 py-2 text-xs rounded-lg transition-colors"
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
            :class="day.completion_rate >= 1 ? 'bg-success' : day.completion_rate > 0 ? 'bg-accent' : 'bg-surface-3'"
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
      <!-- Habit anchor — "After what routine?" (habit stacking) -->
      <div>
        <label class="text-[11px] text-txt-muted mb-1 block">After what existing routine?</label>
        <div class="flex flex-wrap gap-1.5 mb-2">
          <button
            v-for="anchor in ['morning coffee', 'brushing teeth', 'lunch', 'getting home', 'dinner', 'before bed']"
            :key="anchor"
            @click="newHabitTrigger = anchor"
            class="px-2 py-1 text-[11px] rounded-full border transition-colors"
            :class="newHabitTrigger === anchor
              ? 'bg-accent/20 border-accent text-accent'
              : 'border-bdr text-txt-muted hover:border-accent/50'"
          >
            {{ anchor }}
          </button>
        </div>
        <input
          v-model="newHabitTrigger"
          type="text"
          placeholder="Or type a custom anchor..."
          maxlength="200"
          class="input-field text-sm"
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
          class="text-xs px-3 py-2 rounded transition-colors"
          :class="habit.is_active ? 'text-accent hover:bg-accent-bright/10' : 'text-success hover:bg-success/10'"
        >
          {{ habit.is_active ? 'Deactivate' : 'Activate' }}
        </button>
        <button
          v-if="resettingHabit !== habit.id"
          @click="resettingHabit = habit.id"
          class="text-xs text-txt-muted hover:text-red-400 transition-colors px-3 py-2"
        >
          Reset
        </button>
        <div v-else class="flex items-center gap-2 animate-fade-in">
          <button @click="resetSingleHabit(habit.id)" class="text-xs text-red-400 hover:text-red-300 font-medium px-2 py-1.5">Clear logs</button>
          <button @click="resettingHabit = null" class="text-xs text-txt-muted hover:text-txt-primary px-2 py-1.5">Cancel</button>
        </div>
        <button
          v-if="!habit.is_preset"
          @click="deleteCustomHabit(habit)"
          class="text-xs text-txt-muted hover:text-red-400 transition-colors px-3 py-2"
        >
          Delete
        </button>
      </div>
    </div>
  </template>
</template>

<style scoped>
/* Hide native number-input spinner buttons.
   Arrow keys still increment/decrement when the input is focused (native behaviour),
   which is what desktop users want. Mobile never showed spinners anyway. */
input[type="number"]::-webkit-outer-spin-button,
input[type="number"]::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
  appearance: textfield;
}
</style>
