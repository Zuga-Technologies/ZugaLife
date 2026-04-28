<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api, ApiError } from '@core/api/client'
import { habitIcons, habitIconPicker, habitIconCategories, getIcon } from '../icons'
import { ChevronDown, ChevronUp, CircleDot, Trash2 } from 'lucide-vue-next'
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
// Inline "not enough data yet" hint — gentle guidance, not an error.
const habitInsightHint = ref<string | null>(null)
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

const pausedCount = computed(() => {
  if (!habitCheckin.value) return 0
  return habitCheckin.value.habits.filter(h => !h.habit.is_active).length
})

async function fetchHabitCheckin() {
  try {
    const prevDate = habitCheckin.value?.date
    habitCheckin.value = await api.get<DailyCheckInResponse>('/api/life/habits/checkin')
    if (habitCheckin.value) {
      // Day rolled over server-side — wipe stale per-habit amount inputs so
      // yesterday's values don't seed today's check-in row.
      if (prevDate && prevDate !== habitCheckin.value.date) {
        amountInputs.value = {}
      }
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

// Clear-on-focus pattern. iOS Safari refuses to honor select()/setSelectionRange
// reliably when the user taps a populated input — the touchend handler positions
// the cursor wherever the finger landed, regardless of what we did in @focus.
// Solution: clear the value the moment the input is focused. Empty input = no
// cursor-positioning ambiguity. User types fresh. On blur, if they didn't type,
// we restore the prior value so an accidental tap doesn't lose data.
const savedAmount: Record<number, string> = {}

function handleAmountFocus(e: FocusEvent, habitId: number) {
  const el = e.target as HTMLInputElement
  savedAmount[habitId] = el.value
  amountInputs.value[habitId] = ''
}

function handleAmountBlur(item: HabitCheckInItem) {
  const id = item.habit.id
  if (!amountInputs.value[id]) {
    // User didn't type — restore prior value silently, no log update.
    if (savedAmount[id] !== undefined) amountInputs.value[id] = savedAmount[id]
    delete savedAmount[id]
    return
  }
  delete savedAmount[id]
  void updateHabitAmount(item)
}

// Step the value on ↑/↓. Without type="number" the native step behavior
// is gone, so we replicate it here. Empty inputs seed from default_target.
function handleAmountKeydown(item: HabitCheckInItem, e: KeyboardEvent) {
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
  e.preventDefault()
  const current = amountInputs.value[item.habit.id]
  const target = item.habit.default_target
  if (!current) {
    if (target == null) return
    const seeded = e.key === 'ArrowUp'
      ? Number(target) + 1
      : Math.max(0, Number(target) - 1)
    amountInputs.value[item.habit.id] = String(seeded)
    return
  }
  const n = Number(current)
  if (Number.isNaN(n)) return
  const next = e.key === 'ArrowUp' ? n + 1 : Math.max(0, n - 1)
  amountInputs.value[item.habit.id] = String(next)
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

// --- Weekly target editor (moved from Goals tab — habits-feature, lives here) ---
const editingTargetFor = ref<number | null>(null)
const editTargetValue = ref<number | null>(null)

function startEditTarget(habit: HabitDefinition) {
  editingTargetFor.value = habit.id
  editTargetValue.value = habit.weekly_target ?? null
}

async function setWeeklyTarget(habitId: number) {
  habitError.value = null
  // Optimistic — write the value into the local list, close the editor.
  const habit = allHabits.value.find(h => h.id === habitId)
  const previous = habit?.weekly_target ?? null
  if (habit) habit.weekly_target = editTargetValue.value
  editingTargetFor.value = null
  try {
    await api.patch(`/api/life/habits/${habitId}`, {
      weekly_target: editTargetValue.value || null,
    })
    void fetchAllHabits()
  } catch (e) {
    if (habit) habit.weekly_target = previous
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

async function toggleHabitActive(habit: HabitDefinition) {
  habitError.value = null
  // Optimistic flip — both in the manage list AND in the checkin list (so
  // the paused pill / fade appears immediately on the checkin tab too).
  const wasActive = habit.is_active
  habit.is_active = !wasActive
  if (habitCheckin.value) {
    const inCheckin = habitCheckin.value.habits.find(i => i.habit.id === habit.id)
    if (inCheckin) inCheckin.habit.is_active = !wasActive
    if (wasActive) {
      habitCheckin.value.total_count -= 1
    } else {
      habitCheckin.value.total_count += 1
    }
  }
  try {
    await api.patch(`/api/life/habits/${habit.id}`, { is_active: !wasActive })
    void fetchAllHabits()
    void fetchHabitCheckin()
  } catch (e) {
    // Revert
    habit.is_active = wasActive
    if (habitCheckin.value) {
      const inCheckin = habitCheckin.value.habits.find(i => i.habit.id === habit.id)
      if (inCheckin) inCheckin.habit.is_active = wasActive
      habitCheckin.value.total_count += wasActive ? 1 : -1
    }
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
}

async function deleteCustomHabit(habit: HabitDefinition) {
  habitError.value = null
  // Optimistic remove — drop from both lists immediately.
  const idx = allHabits.value.indexOf(habit)
  if (idx >= 0) allHabits.value.splice(idx, 1)
  let checkinIdx = -1
  if (habitCheckin.value) {
    checkinIdx = habitCheckin.value.habits.findIndex(i => i.habit.id === habit.id)
    if (checkinIdx >= 0) {
      const removed = habitCheckin.value.habits.splice(checkinIdx, 1)[0]
      if (removed.habit.is_active) habitCheckin.value.total_count -= 1
      if (removed.logged) habitCheckin.value.completed_count -= 1
    }
  }
  habitSuccess.value = 'Habit deleted.'
  setTimeout(() => { habitSuccess.value = null }, 2000)
  try {
    await api.delete(`/api/life/habits/${habit.id}`)
    void fetchAllHabits()
    void fetchHabitCheckin()
    emit('success')
  } catch (e) {
    // Revert (best-effort — rare path)
    if (idx >= 0) allHabits.value.splice(idx, 0, habit)
    void fetchAllHabits()
    void fetchHabitCheckin()
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
  // Optimistic — close the confirm flow immediately, fire DELETE in background.
  resetConfirm.value = null
  if (habitCheckin.value) {
    for (const item of habitCheckin.value.habits) item.logged = false
    habitCheckin.value.completed_count = 0
  }
  habitSuccess.value = 'Clearing today...'
  setTimeout(() => { habitSuccess.value = null }, 2500)
  try {
    const res = await api.delete<{ deleted: number }>('/api/life/habits/reset/today')
    habitSuccess.value = `Cleared ${res.deleted} check-ins for today.`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    void fetchHabitCheckin()
    void fetchHabitStreaks()
  } catch {
    habitError.value = 'Reset failed.'
    void fetchHabitCheckin()
  }
}

async function resetAllHistory() {
  habitError.value = null
  resetConfirm.value = null
  if (habitCheckin.value) {
    for (const item of habitCheckin.value.habits) item.logged = false
    habitCheckin.value.completed_count = 0
  }
  habitSuccess.value = 'Clearing history...'
  try {
    const res = await api.delete<{ deleted: number }>('/api/life/habits/reset/history')
    habitSuccess.value = `Cleared ${res.deleted} total logs. Fresh start!`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    void fetchHabitCheckin()
    void fetchHabitStreaks()
    void fetchHabitHistory()
  } catch {
    habitError.value = 'Reset failed.'
    void fetchHabitCheckin()
  }
}

// Two-step delete for a whole day in the History view. First click sets
// deletingDay = date, which swaps the row to a Confirm/Cancel pair.
const deletingDay = ref<string | null>(null)

async function deleteHabitDay(logDate: string) {
  habitError.value = null
  deletingDay.value = null
  habitSuccess.value = 'Deleting day...'
  // Optimistic: drop the day from history immediately.
  if (habitHistory.value) {
    habitHistory.value.days = habitHistory.value.days.filter(d => d.date !== logDate)
  }
  try {
    const res = await api.delete<{ deleted: number }>(`/api/life/habits/reset/day/${logDate}`)
    habitSuccess.value = `Cleared ${res.deleted} log${res.deleted === 1 ? '' : 's'} for ${logDate}.`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    void fetchHabitHistory()
    void fetchHabitCheckin()
  } catch (e) {
    habitSuccess.value = null
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
    void fetchHabitHistory()
  }
}

async function resetSingleHabit(habitId: number) {
  habitError.value = null
  resettingHabit.value = null
  // Optimistic: clear "logged" state for this habit in checkin if present.
  if (habitCheckin.value) {
    const item = habitCheckin.value.habits.find(i => i.habit.id === habitId)
    if (item && item.logged) {
      item.logged = false
      habitCheckin.value.completed_count = Math.max(0, habitCheckin.value.completed_count - 1)
    }
  }
  habitSuccess.value = 'Clearing logs...'
  try {
    const res = await api.delete<{ deleted: number; habit: string }>(`/api/life/habits/reset/${habitId}`)
    habitSuccess.value = `Reset "${res.habit}" — ${res.deleted} logs cleared.`
    setTimeout(() => { habitSuccess.value = null }, 2500)
    void fetchHabitCheckin()
    void fetchHabitStreaks()
  } catch {
    habitError.value = 'Reset failed.'
    void fetchHabitCheckin()
  }
}

async function resetInsightsCooldown() {
  habitError.value = null
  try {
    await api.delete('/api/life/habits/reset/insights')
    habitInsightText.value = null
  } catch {
    habitError.value = 'Could not clear insight cooldown.'
  }
}

async function fetchHabitInsight() {
  if (habitInsightLoading.value) return
  habitInsightLoading.value = true
  habitInsightText.value = null
  habitInsightHint.value = null
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
      // Sparse-data gate — show as a soft inline hint, not a red error.
      habitInsightHint.value = (e.body as Record<string, string>).detail ?? 'Log a few more habits and moods this week, then try again.'
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

// Refetch when the tab/window regains visibility. Without this, leaving the
// app open across local midnight (or backgrounding a PWA) leaves yesterday's
// check-in state on screen — the backend's user-tz "today" has rolled but
// the Vue ref still holds the old payload. visibilitychange fires for tab
// switches and PWA foreground; focus catches desktop window-focus changes.
function handleVisible() {
  if (document.visibilityState !== 'visible') return
  void fetchHabitCheckin()
  void fetchHabitStreaks()
}

onMounted(async () => {
  loadingHabits.value = true
  await Promise.all([fetchHabitCheckin(), fetchHabitStreaks(), fetchAllHabits()])
  loadingHabits.value = false
  document.addEventListener('visibilitychange', handleVisible)
  window.addEventListener('focus', handleVisible)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisible)
  window.removeEventListener('focus', handleVisible)
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
            {{ habitCheckin.completed_count }}/{{ habitCheckin.total_count }} active habits done
            <span v-if="pausedCount > 0" class="text-xs text-txt-muted ml-1">· {{ pausedCount }} paused</span>
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
          :class="[
            item.logged ? 'ring-1 ring-success/30' : '',
            !item.habit.is_active ? 'opacity-50' : '',
          ]"
        >
          <button
            @click="toggleHabit(item)"
            :disabled="!item.habit.is_active"
            class="w-6 h-6 rounded-md border-2 flex items-center justify-center transition-colors duration-100 ease-out flex-shrink-0 disabled:cursor-not-allowed"
            :class="item.logged
              ? 'bg-success border-success text-white'
              : 'border-bdr hover:border-accent'"
          >
            <span v-if="item.logged" class="text-xs">&#10003;</span>
          </button>
          <component :is="getIcon(item.habit.emoji)" :size="22" class="flex-shrink-0 text-accent" v-if="getIcon(item.habit.emoji)" />
          <CircleDot v-else :size="22" class="flex-shrink-0 text-accent" />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium text-txt-primary">{{ item.habit.name }}</span>
              <span
                v-if="!item.habit.is_active"
                class="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-surface-3 text-txt-muted"
              >Paused</span>
            </div>
            <p v-if="item.habit.trigger" class="text-[11px] text-txt-muted leading-tight mt-0.5">After {{ item.habit.trigger }}</p>
          </div>
          <div v-if="item.habit.unit" class="flex items-center gap-1.5">
            <input
              type="text"
              inputmode="decimal"
              pattern="[0-9]*\.?[0-9]*"
              :value="amountInputs[item.habit.id] ?? ''"
              @input="amountInputs[item.habit.id] = ($event.target as HTMLInputElement).value.replace(/[^0-9.]/g, '')"
              @focus="handleAmountFocus($event, item.habit.id)"
              @keydown="handleAmountKeydown(item, $event)"
              @blur="handleAmountBlur(item)"
              @keyup.enter="handleAmountBlur(item)"
              :placeholder="item.habit.default_target ? String(item.habit.default_target) : '0'"
              class="w-14 px-1.5 py-1 text-sm text-right rounded-md bg-surface-3 text-txt-primary border border-bdr focus:border-accent focus:outline-none"
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
        <!-- Soft "not enough data" hint — guidance, not error. -->
        <div v-else-if="habitInsightHint" class="mt-3 p-3 rounded-lg bg-info/8 border border-info/15 animate-fade-in">
          <p class="text-xs text-info/90 leading-relaxed">{{ habitInsightHint }}</p>
        </div>
      </div>
      <!-- Reset Today / Reset History / Clear Cooldown moved to Settings to
           avoid duplicate dangerous actions on the habits page. -->
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
    <!-- Skeleton — shape-matched rows so the layout doesn't shift on first load. -->
    <div v-if="!habitHistory" class="space-y-2 animate-fade-in">
      <div v-for="i in 4" :key="i" class="glass-card px-4 py-3">
        <div class="flex items-center justify-between mb-1.5">
          <div class="bg-surface-3 animate-pulse h-3 w-28 rounded"></div>
          <div class="bg-surface-3 animate-pulse h-3 w-10 rounded"></div>
        </div>
        <div class="bg-surface-3 animate-pulse w-full h-1.5 rounded-full"></div>
      </div>
    </div>
    <div v-else-if="habitHistory.days.filter(d => d.completed_count > 0).length === 0" class="glass-card p-6 text-center">
      <p class="text-txt-muted">No habit data yet. Start checking in!</p>
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="day in habitHistory.days.filter(d => d.completed_count > 0)"
        :key="day.date"
        class="glass-card px-4 py-3"
      >
        <div class="flex items-center justify-between mb-1.5 gap-2">
          <span class="text-sm font-medium text-txt-primary">{{ new Date(day.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) }}</span>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span class="text-xs text-txt-muted">{{ day.completed_count }}/{{ day.total_active }}</span>
            <!-- Two-step delete: first click reveals Confirm/Cancel -->
            <template v-if="deletingDay !== day.date">
              <button
                @click="deletingDay = day.date"
                class="text-txt-muted hover:text-red-400 transition-colors p-1 rounded"
                title="Delete this day's logs"
                aria-label="Delete this day's logs"
              >
                <Trash2 :size="14" />
              </button>
            </template>
            <template v-else>
              <button
                @click="deleteHabitDay(day.date)"
                class="text-xs text-red-400 hover:text-red-300 font-medium px-2 py-0.5 rounded"
              >
                Confirm
              </button>
              <button
                @click="deletingDay = null"
                class="text-xs text-txt-muted hover:text-txt-primary px-2 py-0.5 rounded"
              >
                Cancel
              </button>
            </template>
          </div>
        </div>
        <div class="w-full bg-surface-3 rounded-full h-1.5 mb-1.5">
          <div
            class="h-1.5 rounded-full transition-[width,background-color] duration-300 ease-out"
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
        <!-- Expanded categories — bordered panel so the floating grid feels grounded -->
        <div
          v-if="showMoreIcons"
          class="mt-2 p-3 rounded-lg border border-bdr/60 bg-surface-2/40 max-h-60 overflow-y-auto space-y-3 animate-fade-in"
        >
          <div v-for="(cat, ci) in habitIconCategories" :key="cat.label" :class="ci > 0 ? 'pt-3 border-t border-bdr/30' : ''">
            <p class="text-[11px] text-txt-muted uppercase tracking-wider mb-1.5">{{ cat.label }}</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="opt in cat.icons"
                :key="opt.name"
                @click="newHabitIcon = opt.name"
                class="w-9 h-9 rounded-lg flex items-center justify-center transition-colors duration-100"
                :class="newHabitIcon === opt.name ? 'bg-accent/15 ring-1 ring-accent/50 text-accent' : 'bg-surface-3 text-txt-muted hover:text-txt-primary'"
                :title="opt.label"
              >
                <component :is="opt.icon" :size="18" />
              </button>
            </div>
          </div>
        </div>
      </div>
      <!-- Unit selection — pills for common units (matches the anchor row pattern
           below) plus a custom-text fallback. Replaces the native <datalist>
           dropdown that browsers rendered in inconsistent / ugly styles. -->
      <div>
        <label class="text-[11px] text-txt-muted mb-1 block">How will you measure it?</label>
        <div class="flex flex-wrap gap-1.5 mb-2">
          <button
            type="button"
            @click="newHabitUnit = ''"
            class="px-2.5 py-1 text-[11px] rounded-full border transition-colors"
            :class="!newHabitUnit
              ? 'bg-accent/20 border-accent text-accent'
              : 'border-bdr text-txt-muted hover:border-accent/50'"
          >Just check off</button>
          <button
            type="button"
            v-for="u in habitUnits"
            :key="u.value"
            @click="newHabitUnit = u.value"
            class="px-2.5 py-1 text-[11px] rounded-full border transition-colors"
            :class="newHabitUnit === u.value
              ? 'bg-accent/20 border-accent text-accent'
              : 'border-bdr text-txt-muted hover:border-accent/50'"
            :title="u.label"
          >{{ u.value }}</button>
        </div>
        <div class="flex gap-2">
          <input
            v-model="newHabitUnit"
            type="text"
            placeholder="Or type a custom unit"
            class="input-field flex-1 text-sm"
            maxlength="20"
          />
          <input
            v-if="newHabitUnit"
            v-model.number="newHabitTarget"
            type="number"
            placeholder="Target"
            min="1"
            class="input-field w-24 text-sm"
          />
        </div>
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

    <!-- Habit list — mobile uses a card with a divided action bar; sm+ keeps a single horizontal row -->
    <div class="space-y-2">
      <div
        v-for="habit in allHabits"
        :key="habit.id"
        class="glass-card overflow-hidden flex flex-col sm:flex-row sm:items-center sm:gap-3 sm:px-4 sm:py-3"
        :class="!habit.is_active ? 'opacity-50' : ''"
      >
        <!-- Header: icon + name + meta (with target pill inline) -->
        <div class="flex items-center gap-3 min-w-0 flex-1 px-4 py-3 sm:p-0">
          <component :is="getIcon(habit.emoji)" :size="22" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
          <CircleDot v-else :size="22" class="text-accent flex-shrink-0" />
          <div class="min-w-0 flex-1">
            <span class="text-sm font-medium text-txt-primary block truncate">{{ habit.name }}</span>
            <div class="flex items-center gap-x-2 gap-y-1 flex-wrap mt-0.5">
              <span v-if="habit.unit" class="text-xs text-txt-muted">{{ habit.default_target }} {{ habit.unit }}</span>
              <span v-if="habit.unit && habit.is_preset" class="text-xs text-txt-muted/60">·</span>
              <span v-if="habit.is_preset" class="text-xs text-txt-muted">preset</span>
              <!-- Target pill: editor inline when editing, pill button otherwise. Sits with the meta on mobile so the action bar reads as 'actions only'. -->
              <template v-if="editingTargetFor === habit.id">
                <select
                  v-model.number="editTargetValue"
                  @change="setWeeklyTarget(habit.id)"
                  @blur="setWeeklyTarget(habit.id)"
                  class="input-field w-32 text-xs"
                >
                  <option :value="null">No target</option>
                  <option v-for="n in 7" :key="n" :value="n">{{ n }}x / week</option>
                </select>
              </template>
              <button
                v-else
                @click="startEditTarget(habit)"
                class="text-[11px] px-2 py-0.5 rounded-full border border-bdr text-txt-muted hover:text-accent hover:border-accent/50 transition-colors whitespace-nowrap"
                :title="habit.weekly_target ? 'Change weekly target' : 'Set a weekly target'"
              >
                {{ habit.weekly_target ? habit.weekly_target + 'x / week' : 'No target' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Action bar: divided on mobile (full-width row, evenly spaced), inline on sm+ -->
        <div class="flex items-stretch border-t border-bdr/60 sm:border-t-0 sm:items-center sm:gap-2 sm:flex-shrink-0">
          <button
            @click="toggleHabitActive(habit)"
            class="flex-1 sm:flex-none text-xs px-3 py-2.5 sm:py-2 rounded-none sm:rounded transition-colors whitespace-nowrap"
            :class="habit.is_active ? 'text-accent hover:bg-accent-bright/10' : 'text-success hover:bg-success/10'"
          >
            {{ habit.is_active ? 'Deactivate' : 'Activate' }}
          </button>
          <span class="w-px bg-bdr/60 sm:hidden" />
          <template v-if="resettingHabit !== habit.id">
            <button
              @click="resettingHabit = habit.id"
              class="flex-1 sm:flex-none text-xs text-txt-muted hover:text-red-400 transition-colors px-3 py-2.5 sm:py-2"
            >
              Reset
            </button>
          </template>
          <template v-else>
            <button
              @click="resetSingleHabit(habit.id)"
              class="flex-1 sm:flex-none text-xs text-red-400 hover:text-red-300 font-medium px-2 py-2.5 sm:py-1.5"
            >Clear logs</button>
            <span class="w-px bg-bdr/60 sm:hidden" />
            <button
              @click="resettingHabit = null"
              class="flex-1 sm:flex-none text-xs text-txt-muted hover:text-txt-primary px-2 py-2.5 sm:py-1.5"
            >Cancel</button>
          </template>
          <span v-if="!habit.is_preset" class="w-px bg-bdr/60 sm:hidden" />
          <button
            v-if="!habit.is_preset"
            @click="deleteCustomHabit(habit)"
            class="flex-1 sm:flex-none text-xs text-txt-muted hover:text-red-400 transition-colors px-3 py-2.5 sm:py-2"
          >
            Delete
          </button>
        </div>
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
