<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ApiError } from '@core/api/client'
import { CircleDot, Pencil } from 'lucide-vue-next'
import { getIcon } from '../icons'
import { useLifeShared } from '../composables/useLifeShared'
import WoopGoalWizard from '../components/WoopGoalWizard.vue'

const emit = defineEmits<{
  (e: 'success'): void
}>()

const {
  withCelebration,
  handleInsufficientTokens,
  handleServiceError,
  notifyTokenSpend,
  parseUTC,
} = useLifeShared()

// ── Types ──────────────────────────────────────────────────────

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
  full_target: number | null
  can_escalate: boolean
}

interface GoalMilestone {
  id: number
  goal_id: number
  title: string
  is_completed: boolean
  sort_order: number
  created_at: string
  completed_at: string | null
}

interface LinkedHabit {
  habit_id: number
  habit_name: string
  habit_emoji: string
  days_completed: number
  days_total: number
}

interface Goal {
  id: number
  title: string
  description: string | null
  deadline: string | null
  is_completed: boolean
  sort_order: number
  completed_at: string | null
  created_at: string
  updated_at: string
  template_key: string | null
  // WOOP fields
  identity_statement: string | null
  obstacle: string | null
  implementation_plan: string | null
  approach_reframe: string | null
  milestones: GoalMilestone[]
  milestone_count: number
  milestone_done: number
  linked_habits: LinkedHabit[]
}

interface GoalListResponse {
  active: Goal[]
  completed: Goal[]
}

interface GoalTemplate {
  key: string
  title: string
  description: string
  suggested_habits: string[]
  already_adopted: boolean
}

interface WeeklyTargetItem {
  habit_id: number
  habit_name: string
  habit_emoji: string
  weekly_target: number
  this_week_count: number
  progress_pct: number
}

interface WeeklyTargetsResponse {
  habits: WeeklyTargetItem[]
  week_start: string
}

// ── State ──────────────────────────────────────────────────────

type GoalSubView = 'goals' | 'weekly'
const goalSubView = ref<GoalSubView>('goals')

const activeGoals = ref<Goal[]>([])
const completedGoals = ref<Goal[]>([])
const weeklyTargets = ref<WeeklyTargetItem[]>([])
const loadingGoals = ref(true)
const goalError = ref<string | null>(null)
const goalSuccess = ref<string | null>(null)

// Create goal form
type GoalCreateMode = 'none' | 'templates' | 'custom' | 'woop'
const goalCreateMode = ref<GoalCreateMode>('none')
const goalTemplates = ref<GoalTemplate[]>([])
const templateAdopting = ref<string | null>(null)
const newGoalTitle = ref('')
const newGoalDescription = ref('')
const newGoalDeadline = ref('')
const goalSubmitting = ref(false)

// Expanded goals (to show milestones)
const expandedGoals = ref<Set<number>>(new Set())

// Add milestone form (per goal)
const addingMilestoneTo = ref<number | null>(null)
const newMilestoneTitle = ref('')

// Habit linking
const linkingHabitTo = ref<number | null>(null)
const allHabits = ref<HabitDefinition[]>([])

// Editing goal
const editingGoalId = ref<number | null>(null)
const editGoalTitle = ref('')
const editGoalDescription = ref('')
const editGoalDeadline = ref('')
const editGoalSaving = ref(false)

// Editing weekly target
const editingTargetFor = ref<number | null>(null)
const editTargetValue = ref<number | null>(null)

// AI goal insight
const goalInsightLoading = ref<number | null>(null)
const goalInsights = ref<Record<number, string>>({})

// Active goal cap
const MAX_ACTIVE_GOALS = 3
const showBacklogGoals = ref(false)

const priorityGoals = computed(() => activeGoals.value.slice(0, MAX_ACTIVE_GOALS))
const backlogGoals = computed(() => activeGoals.value.slice(MAX_ACTIVE_GOALS))

// ── Fetch ──────────────────────────────────────────────────────

async function fetchGoals() {
  try {
    const res = await api.get<GoalListResponse>('/api/life/goals')
    activeGoals.value = res.active
    completedGoals.value = res.completed
  } catch { /* silent */ }
}

async function fetchGoalTemplates() {
  try {
    goalTemplates.value = await api.get<GoalTemplate[]>('/api/life/goals/templates')
  } catch { /* silent */ }
}

async function fetchWeeklyTargets() {
  try {
    const res = await api.get<WeeklyTargetsResponse>('/api/life/habits/weekly')
    weeklyTargets.value = res.habits
  } catch { /* silent */ }
}

async function fetchAllHabits() {
  try {
    allHabits.value = await api.get<HabitDefinition[]>('/api/life/habits')
  } catch { /* silent */ }
}

// ── Goal helpers ───────────────────────────────────────────────

function toggleGoalExpand(id: number) {
  if (expandedGoals.value.has(id)) {
    expandedGoals.value.delete(id)
  } else {
    expandedGoals.value.add(id)
  }
}

function startEditGoal(goal: Goal) {
  editingGoalId.value = goal.id
  editGoalTitle.value = goal.title
  editGoalDescription.value = goal.description || ''
  editGoalDeadline.value = goal.deadline || ''
  expandedGoals.value.add(goal.id)
}

function cancelEditGoal() {
  editingGoalId.value = null
  editGoalTitle.value = ''
  editGoalDescription.value = ''
  editGoalDeadline.value = ''
}

async function saveEditGoal(goalId: number) {
  if (!editGoalTitle.value.trim() || editGoalSaving.value) return
  editGoalSaving.value = true
  goalError.value = null
  try {
    await api.patch(`/api/life/goals/${goalId}`, {
      title: editGoalTitle.value.trim(),
      description: editGoalDescription.value.trim() || null,
      deadline: editGoalDeadline.value || null,
    })
    editingGoalId.value = null
    goalSuccess.value = 'Goal updated!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
    emit('success')
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    editGoalSaving.value = false
  }
}

async function adoptTemplate(key: string) {
  if (templateAdopting.value) return
  templateAdopting.value = key
  goalError.value = null
  try {
    await api.post('/api/life/goals/from-template', { template_key: key })
    goalSuccess.value = 'Goal created from template!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    goalCreateMode.value = 'none'
    await Promise.all([fetchGoals(), fetchGoalTemplates()])
    emit('success')
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    templateAdopting.value = null
  }
}

function availableHabitsForGoal(goal: Goal): HabitDefinition[] {
  const linkedIds = new Set(goal.linked_habits.map(h => h.habit_id))
  return allHabits.value.filter(h => h.is_active && !linkedIds.has(h.id))
}

async function linkHabit(goalId: number, habitId: number) {
  goalError.value = null
  // Optimistic — close the linker dropdown immediately, refetch in bg.
  linkingHabitTo.value = null
  try {
    await api.post(`/api/life/goals/${goalId}/habits`, { habit_id: habitId })
    void fetchGoals()
  } catch (e) {
    void fetchGoals()
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function unlinkHabit(goalId: number, habitId: number) {
  goalError.value = null
  // Optimistic — drop the chip from the goal's linked-habit list.
  const goal = goals.value.find(g => g.id === goalId)
  let removedHabit: any = null
  let removedIdx = -1
  if (goal && goal.linked_habits) {
    removedIdx = goal.linked_habits.findIndex(h => h.id === habitId)
    if (removedIdx >= 0) removedHabit = goal.linked_habits.splice(removedIdx, 1)[0]
  }
  try {
    await api.delete(`/api/life/goals/${goalId}/habits/${habitId}`)
    void fetchGoals()
  } catch (e) {
    if (goal && removedHabit && removedIdx >= 0) {
      goal.linked_habits.splice(removedIdx, 0, removedHabit)
    }
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function createGoal() {
  if (!newGoalTitle.value.trim() || goalSubmitting.value) return
  goalSubmitting.value = true
  goalError.value = null
  try {
    await api.post('/api/life/goals', {
      title: newGoalTitle.value.trim(),
      description: newGoalDescription.value.trim() || null,
      deadline: newGoalDeadline.value || null,
    })
    newGoalTitle.value = ''
    newGoalDescription.value = ''
    newGoalDeadline.value = ''
    goalCreateMode.value = 'none'
    goalSuccess.value = 'Goal created!'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
    emit('success')
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    goalSubmitting.value = false
  }
}

async function createWoopGoal(goalData: {
  title: string
  description: string | null
  deadline: string | null
  identity_statement: string | null
  obstacle: string | null
  implementation_plan: string | null
  approach_reframe: string | null
}) {
  goalSubmitting.value = true
  goalError.value = null
  try {
    await api.post('/api/life/goals', goalData)
    goalCreateMode.value = 'none'
    goalSuccess.value = 'Goal created with your plan!'
    setTimeout(() => { goalSuccess.value = null }, 3000)
    await fetchGoals()
    emit('success')
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  } finally {
    goalSubmitting.value = false
  }
}

async function toggleGoalComplete(goal: Goal) {
  goalError.value = null
  try {
    await api.patch(`/api/life/goals/${goal.id}/complete`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function deleteGoal(goal: Goal) {
  goalError.value = null
  // Optimistic — drop the goal from the list immediately.
  const idx = goals.value.indexOf(goal)
  if (idx >= 0) goals.value.splice(idx, 1)
  goalSuccess.value = 'Goal deleted.'
  setTimeout(() => { goalSuccess.value = null }, 2000)
  try {
    await api.delete(`/api/life/goals/${goal.id}`)
    void fetchGoals()
    emit('success')
  } catch (e) {
    if (idx >= 0) goals.value.splice(idx, 0, goal)
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function addMilestone(goalId: number) {
  if (!newMilestoneTitle.value.trim()) return
  goalError.value = null
  try {
    await api.post(`/api/life/goals/${goalId}/milestones`, {
      title: newMilestoneTitle.value.trim(),
    })
    newMilestoneTitle.value = ''
    addingMilestoneTo.value = null
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function toggleMilestone(goalId: number, milestone: GoalMilestone) {
  goalError.value = null
  // Optimistic — flip the milestone's state and progress count immediately.
  const goal = goals.value.find(g => g.id === goalId)
  const wasCompleted = milestone.is_completed
  milestone.is_completed = !wasCompleted
  if (goal) {
    goal.milestone_done += wasCompleted ? -1 : 1
  }
  try {
    await api.patch(`/api/life/goals/${goalId}/milestones/${milestone.id}`, {
      is_completed: !wasCompleted,
    })
    void fetchGoals()
  } catch (e) {
    // Revert on error
    milestone.is_completed = wasCompleted
    if (goal) goal.milestone_done += wasCompleted ? 1 : -1
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function deleteMilestone(goalId: number, milestoneId: number) {
  goalError.value = null
  try {
    await api.delete(`/api/life/goals/${goalId}/milestones/${milestoneId}`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function setWeeklyTarget(habitId: number) {
  goalError.value = null
  try {
    await api.patch(`/api/life/habits/${habitId}`, {
      weekly_target: editTargetValue.value || null,
    })
    editingTargetFor.value = null
    editTargetValue.value = null
    await fetchWeeklyTargets()
    await fetchAllHabits()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

function startEditTarget(habit: HabitDefinition) {
  editingTargetFor.value = habit.id
  editTargetValue.value = habit.weekly_target ?? null
}

function goalMilestonePct(goal: Goal): number {
  if (goal.milestone_count === 0) return 0
  return Math.round((goal.milestone_done / goal.milestone_count) * 100)
}

function isOverdue(deadline: string | null): boolean {
  if (!deadline) return false
  return new Date(deadline + 'T23:59:59') < new Date()
}

function daysUntilDeadline(deadline: string | null): number | null {
  if (!deadline) return null
  const dl = new Date(deadline + 'T23:59:59')
  return Math.ceil((dl.getTime() - Date.now()) / 86400000)
}

function deadlineLabel(deadline: string | null): string {
  const days = daysUntilDeadline(deadline)
  if (days === null) return ''
  if (days < 0) return `${Math.abs(days)}d overdue`
  if (days === 0) return 'Due today'
  if (days === 1) return 'Due tomorrow'
  if (days <= 7) return `${days}d left`
  if (days <= 30) return `${Math.ceil(days / 7)}w left`
  return `${Math.ceil(days / 30)}mo left`
}

function projectedCompletion(goal: Goal): string | null {
  if (goal.milestone_count === 0 || goal.milestone_done === 0) return null
  const created = new Date(goal.created_at).getTime()
  const elapsed = Date.now() - created
  const rate = goal.milestone_done / elapsed
  const remaining = goal.milestone_count - goal.milestone_done
  const msToComplete = remaining / rate
  const projected = new Date(Date.now() + msToComplete)
  return projected.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function paceStatus(goal: Goal): 'ahead' | 'behind' | 'on-track' | null {
  if (!goal.deadline || goal.milestone_count === 0) return null
  const created = new Date(goal.created_at).getTime()
  const deadline = new Date(goal.deadline + 'T23:59:59').getTime()
  const totalTime = deadline - created
  const elapsed = Date.now() - created
  if (totalTime <= 0) return null
  const expectedPct = Math.min(100, (elapsed / totalTime) * 100)
  const actualPct = goalMilestonePct(goal)
  const diff = actualPct - expectedPct
  if (diff >= 10) return 'ahead'
  if (diff <= -10) return 'behind'
  return 'on-track'
}

async function fetchGoalInsight(goalId: number) {
  if (goalInsightLoading.value) return
  goalInsightLoading.value = goalId
  try {
    const res = await api.post<{ insight: string; cost: number }>(`/api/life/goals/${goalId}/insight`)
    goalInsights.value[goalId] = res.insight
    notifyTokenSpend()
  } catch (e) {
    if (e instanceof ApiError && e.status === 402) {
      goalInsights.value[goalId] = handleInsufficientTokens('Goal Coaching')
    } else if (e instanceof ApiError && e.status >= 500) {
      goalInsights.value[goalId] = handleServiceError('Service Unavailable', 'The AI service is temporarily down. Your tokens were not charged. Please try again in a few minutes.')
    } else {
      goalInsights.value[goalId] = handleServiceError('Generation Failed', 'Could not generate your goal coaching insight right now. Please try again.')
    }
  } finally {
    goalInsightLoading.value = null
  }
}

async function recommitGoal(goalId: number) {
  try {
    await api.post(`/api/life/goals/${goalId}/recommit`, {})
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? 'Recommit failed'
    }
  }
}

// ── Lifecycle ──────────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([
    fetchGoals(),
    fetchGoalTemplates(),
    fetchWeeklyTargets(),
    fetchAllHabits(),
  ])
  loadingGoals.value = false
})
</script>

<template>
  <!-- Sub-nav -->
  <div class="flex gap-3 mb-6">
    <button
      v-for="view in [
        { key: 'goals', label: 'Life Goals' },
        { key: 'weekly', label: 'Weekly Targets' },
      ] as { key: GoalSubView; label: string }[]"
      :key="view.key"
      @click="goalSubView = view.key; if (view.key === 'weekly') fetchWeeklyTargets()"
      class="px-4 py-2.5 text-xs font-medium rounded-lg transition-colors"
      :class="goalSubView === view.key ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
    >
      {{ view.label }}
    </button>
  </div>

  <p v-if="goalError" class="text-sm text-red-400 mb-4">{{ goalError }}</p>

  <!-- ===== LIFE GOALS SUB-VIEW ===== -->
  <template v-if="goalSubView === 'goals'">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-txt-primary">Life Goals</h2>
      <button
        @click="goalCreateMode = goalCreateMode === 'none' ? 'templates' : 'none'"
        class="text-sm text-accent hover:text-accent/80 transition-colors"
      >
        {{ goalCreateMode !== 'none' ? 'Cancel' : '+ New Goal' }}
      </button>
    </div>

    <!-- Template picker -->
    <div v-if="goalCreateMode === 'templates'" class="mb-4 space-y-3 animate-fade-in">
      <div class="grid grid-cols-2 gap-2">
        <button
          v-for="tmpl in goalTemplates.filter(t => !t.already_adopted)"
          :key="tmpl.key"
          @click="adoptTemplate(tmpl.key)"
          :disabled="templateAdopting !== null"
          class="glass-card p-3 text-left hover:border-accent/50 transition-all cursor-pointer"
        >
          <span class="text-sm font-medium text-txt-primary block">{{ tmpl.title }}</span>
          <span class="text-xs text-txt-muted mt-1 block line-clamp-2">{{ tmpl.description }}</span>
          <div v-if="tmpl.suggested_habits.length > 0" class="mt-2 flex flex-wrap gap-1">
            <span
              v-for="h in tmpl.suggested_habits"
              :key="h"
              class="text-[10px] bg-surface-3 text-txt-muted px-1.5 py-0.5 rounded"
            >{{ h }}</span>
          </div>
          <span v-if="templateAdopting === tmpl.key" class="text-xs text-accent mt-1 block">Creating...</span>
        </button>
      </div>
      <div class="flex justify-center gap-4">
        <button
          @click="goalCreateMode = 'woop'"
          class="text-xs text-accent hover:text-accent/80 transition-colors font-medium"
        >
          Guided goal wizard &rarr;
        </button>
        <button
          @click="goalCreateMode = 'custom'"
          class="text-xs text-txt-muted hover:text-accent transition-colors"
        >
          Quick create &rarr;
        </button>
      </div>
    </div>

    <!-- WOOP Goal Wizard -->
    <div v-if="goalCreateMode === 'woop'" class="glass-card mb-4 animate-fade-in">
      <WoopGoalWizard
        @create="createWoopGoal"
        @cancel="goalCreateMode = 'none'"
      />
    </div>

    <!-- Custom goal form -->
    <div v-if="goalCreateMode === 'custom'" class="glass-card p-4 mb-4 space-y-3 animate-fade-in">
      <input
        v-model="newGoalTitle"
        type="text"
        placeholder="What do you want to achieve?"
        maxlength="200"
        class="input-field"
      />
      <textarea
        v-model="newGoalDescription"
        placeholder="Description (optional)"
        maxlength="2000"
        rows="3"
        class="input-field resize-none text-sm"
      />
      <div class="flex items-center gap-2">
        <label class="text-xs text-txt-muted">Deadline:</label>
        <input
          v-model="newGoalDeadline"
          type="date"
          class="input-field flex-1 text-sm"
        />
      </div>
      <div class="flex gap-2">
        <button
          @click="createGoal"
          :disabled="!newGoalTitle.trim() || goalSubmitting"
          class="btn-primary flex-1 text-sm"
        >
          {{ goalSubmitting ? 'Creating...' : 'Create Goal' }}
        </button>
        <button
          @click="goalCreateMode = 'templates'"
          class="text-xs text-txt-muted hover:text-accent transition-colors px-3"
        >
          &larr;
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loadingGoals" class="text-sm text-txt-muted">Loading goals...</div>

    <!-- Empty state -->
    <div v-else-if="activeGoals.length === 0 && completedGoals.length === 0" class="glass-card p-8 text-center">
      <p class="text-lg mb-2">No goals yet</p>
      <p class="text-txt-muted text-sm">Pick a template above or create a custom goal.</p>
    </div>

    <!-- Active goals (capped at 3, rest in backlog) -->
    <div v-else class="space-y-3">
      <div
        v-for="goal in priorityGoals"
        :key="goal.id"
        class="glass-card overflow-hidden animate-slide-up"
      >
        <!-- Goal header: edit mode -->
        <div v-if="editingGoalId === goal.id" class="px-4 py-3 space-y-2">
          <input
            v-model="editGoalTitle"
            type="text"
            placeholder="Goal title"
            maxlength="200"
            class="input-field w-full text-sm font-medium"
            @keyup.enter="saveEditGoal(goal.id)"
          />
          <textarea
            v-model="editGoalDescription"
            placeholder="Description (optional)"
            maxlength="2000"
            rows="2"
            class="input-field w-full text-sm resize-none"
          />
          <div class="flex items-center gap-2">
            <label class="text-xs text-txt-muted">Deadline:</label>
            <input
              v-model="editGoalDeadline"
              type="date"
              class="input-field text-sm flex-1"
            />
          </div>
          <div class="flex items-center gap-2 pt-1">
            <button
              @click="saveEditGoal(goal.id)"
              :disabled="!editGoalTitle.trim() || editGoalSaving"
              class="text-xs text-accent hover:text-accent/80 disabled:opacity-40"
            >
              {{ editGoalSaving ? 'Saving...' : 'Save' }}
            </button>
            <button @click="cancelEditGoal()" class="text-xs text-txt-muted hover:text-txt-primary">Cancel</button>
          </div>
        </div>

        <!-- Goal header: display mode -->
        <div v-else class="px-4 py-3 flex items-start gap-3 group/goal">
          <button
            @click="toggleGoalComplete(goal)"
            class="w-5 h-5 rounded-full border-2 border-bdr hover:border-accent flex-shrink-0 mt-0.5 transition-colors"
          />
          <div class="flex-1 min-w-0 cursor-pointer" @click="toggleGoalExpand(goal.id)">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-medium text-txt-primary">{{ goal.title }}</span>
              <button
                @click.stop="startEditGoal(goal)"
                class="opacity-0 group-hover/goal:opacity-100 p-0.5 rounded text-txt-muted hover:text-accent transition-all"
                title="Edit goal"
              >
                <Pencil :size="12" />
              </button>
              <!-- Deadline countdown -->
              <span
                v-if="goal.deadline"
                class="text-[11px] px-1.5 py-0.5 rounded font-medium"
                :class="isOverdue(goal.deadline)
                  ? 'bg-red-500/15 text-red-400'
                  : daysUntilDeadline(goal.deadline)! <= 7
                    ? 'bg-accent/15 text-accent'
                    : 'bg-surface-3 text-txt-muted'"
              >
                {{ deadlineLabel(goal.deadline) }}
              </span>
              <!-- Pace status badge -->
              <span
                v-if="paceStatus(goal)"
                class="text-[10px] px-1.5 py-0.5 rounded font-semibold"
                :class="{
                  'bg-success/15 text-success': paceStatus(goal) === 'ahead',
                  'bg-accent/15 text-accent': paceStatus(goal) === 'on-track',
                  'bg-red-500/15 text-red-400': paceStatus(goal) === 'behind',
                }"
              >
                {{ paceStatus(goal) === 'ahead' ? 'AHEAD' : paceStatus(goal) === 'behind' ? 'BEHIND' : 'ON TRACK' }}
              </span>
            </div>
            <p v-if="goal.description" class="text-xs text-txt-muted mt-1 line-clamp-2">{{ goal.description }}</p>

            <!-- Overdue recommit banner -->
            <div v-if="isOverdue(goal.deadline)" class="mt-2 p-2 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center gap-2">
              <span class="text-xs text-red-400">Deadline passed.</span>
              <button
                @click.stop="recommitGoal(goal.id)"
                class="text-xs font-medium text-accent hover:text-accent/80 transition-colors"
              >
                Recommit (+30 days)
              </button>
            </div>

            <!-- Milestone progress bar -->
            <div v-if="goal.milestone_count > 0" class="mt-2">
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-txt-muted">{{ goal.milestone_done }}/{{ goal.milestone_count }} milestones</span>
                <div class="flex items-center gap-2">
                  <span v-if="projectedCompletion(goal)" class="text-[10px] text-txt-muted">
                    Est. {{ projectedCompletion(goal) }}
                  </span>
                  <span class="text-xs text-txt-muted">{{ goalMilestonePct(goal) }}%</span>
                </div>
              </div>
              <div class="w-full bg-surface-3 rounded-full h-1.5">
                <div
                  class="h-1.5 rounded-full transition-[width,background-color] duration-300 ease-out"
                  :class="goalMilestonePct(goal) === 100 ? 'bg-success' : 'bg-accent'"
                  :style="{ width: goalMilestonePct(goal) + '%' }"
                />
              </div>
            </div>
          </div>
          <button
            @click="toggleGoalExpand(goal.id)"
            class="text-txt-muted hover:text-txt-primary transition-colors text-xs px-1"
          >
            {{ expandedGoals.has(goal.id) ? '&#9650;' : '&#9660;' }}
          </button>
        </div>

        <!-- Expanded: linked habits + milestones + actions -->
        <div v-if="expandedGoals.has(goal.id)" class="border-t border-bdr px-4 py-3 space-y-3 animate-fade-in">

          <!-- WOOP Psychology Fields -->
          <div v-if="goal.identity_statement || goal.obstacle || goal.implementation_plan" class="space-y-2 pb-2 border-b border-bdr/50">
            <div v-if="goal.identity_statement" class="flex gap-2">
              <span class="text-[10px] font-bold uppercase text-accent-alt w-16 flex-shrink-0 pt-0.5">Identity</span>
              <p class="text-xs text-txt-secondary">{{ goal.identity_statement }}</p>
            </div>
            <div v-if="goal.obstacle" class="flex gap-2">
              <span class="text-[10px] font-bold uppercase text-red-400 w-16 flex-shrink-0 pt-0.5">Obstacle</span>
              <p class="text-xs text-txt-secondary">{{ goal.obstacle }}</p>
            </div>
            <div v-if="goal.implementation_plan" class="flex gap-2">
              <span class="text-[10px] font-bold uppercase text-success w-16 flex-shrink-0 pt-0.5">Plan</span>
              <p class="text-xs text-txt-secondary">{{ goal.implementation_plan }}</p>
            </div>
          </div>

          <!-- Linked habits -->
          <div v-if="goal.linked_habits.length > 0" class="space-y-1.5">
            <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide">Linked Habits</p>
            <div v-for="lh in goal.linked_habits" :key="lh.habit_id" class="flex items-center gap-2 group">
              <component :is="getIcon(lh.habit_emoji)" :size="16" class="text-accent flex-shrink-0" v-if="getIcon(lh.habit_emoji)" />
              <CircleDot v-else :size="16" class="text-accent flex-shrink-0" />
              <span class="text-sm text-txt-primary flex-1">{{ lh.habit_name }}</span>
              <div class="flex gap-0.5">
                <div
                  v-for="d in lh.days_total"
                  :key="d"
                  class="w-3 h-3 rounded-sm"
                  :class="d <= lh.days_completed ? 'bg-success' : 'bg-surface-3'"
                />
              </div>
              <span class="text-xs text-txt-muted w-8 text-right">{{ lh.days_completed }}/{{ lh.days_total }}</span>
              <button
                @click="unlinkHabit(goal.id, lh.habit_id)"
                class="text-xs text-txt-muted/40 hover:text-red-400 transition-colors px-2 py-1"
              >&times;</button>
            </div>
          </div>

          <!-- Link habit picker -->
          <div v-if="linkingHabitTo === goal.id" class="space-y-1.5">
            <p class="text-xs text-txt-muted">Select a habit to link:</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="h in availableHabitsForGoal(goal)"
                :key="h.id"
                @click="linkHabit(goal.id, h.id)"
                class="text-xs bg-surface-3 hover:bg-accent/15 text-txt-primary px-2 py-1 rounded transition-colors"
              >
                <component :is="getIcon(h.emoji)" :size="14" class="inline-block" v-if="getIcon(h.emoji)" /><CircleDot v-else :size="14" class="inline-block" /> {{ h.name }}
              </button>
              <span v-if="availableHabitsForGoal(goal).length === 0" class="text-xs text-txt-muted">No unlinked habits available</span>
            </div>
          </div>

          <!-- Milestones -->
          <div v-if="goal.milestones.length > 0" class="space-y-1.5">
            <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide">Milestones</p>
            <div v-for="ms in goal.milestones" :key="ms.id" class="flex items-center gap-2 group">
              <button
                @click="toggleMilestone(goal.id, ms)"
                class="w-4 h-4 rounded border flex items-center justify-center transition-colors duration-100 ease-out flex-shrink-0"
                :class="ms.is_completed
                  ? 'bg-success border-success text-white'
                  : 'border-bdr hover:border-accent'"
              >
                <span v-if="ms.is_completed" class="text-[10px]">&#10003;</span>
              </button>
              <span
                class="text-sm flex-1"
                :class="ms.is_completed ? 'text-txt-muted line-through' : 'text-txt-primary'"
              >
                {{ ms.title }}
              </span>
              <button
                @click="deleteMilestone(goal.id, ms.id)"
                class="text-xs text-txt-muted/40 hover:text-red-400 transition-colors px-2 py-1"
              >
                &times;
              </button>
            </div>
          </div>

          <!-- Add milestone -->
          <div v-if="addingMilestoneTo === goal.id" class="flex gap-2 mt-2">
            <input
              v-model="newMilestoneTitle"
              type="text"
              placeholder="Milestone title"
              maxlength="200"
              class="input-field flex-1 text-sm"
              @keyup.enter="addMilestone(goal.id)"
            />
            <button @click="addMilestone(goal.id)" class="text-sm text-accent hover:text-accent/80">Add</button>
            <button @click="addingMilestoneTo = null; newMilestoneTitle = ''" class="text-sm text-txt-muted">Cancel</button>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-3 pt-2 border-t border-bdr/50">
            <button
              v-if="linkingHabitTo !== goal.id"
              @click="linkingHabitTo = goal.id"
              class="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              + Link Habit
            </button>
            <button
              v-else
              @click="linkingHabitTo = null"
              class="text-xs text-txt-muted"
            >
              Done linking
            </button>
            <button
              v-if="addingMilestoneTo !== goal.id"
              @click="addingMilestoneTo = goal.id; newMilestoneTitle = ''"
              class="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              + Add Milestone
            </button>
            <button
              v-if="editingGoalId !== goal.id"
              @click="startEditGoal(goal)"
              class="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              Edit
            </button>
            <button
              @click="fetchGoalInsight(goal.id)"
              :disabled="goalInsightLoading === goal.id"
              class="text-xs text-accent-alt hover:text-accent-alt-bright transition-colors"
            >
              {{ goalInsightLoading === goal.id ? 'Analyzing...' : 'AI Insight' }}
            </button>
            <button
              @click="deleteGoal(goal)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors ml-auto"
            >
              Delete Goal
            </button>
          </div>

          <!-- AI Insight display -->
          <div v-if="goalInsights[goal.id]" class="mt-2 p-3 rounded-lg bg-accent-alt/10 border border-accent-alt/20">
            <p class="text-xs text-txt-secondary leading-relaxed">{{ goalInsights[goal.id] }}</p>
          </div>
        </div>
      </div>

      <!-- Backlog goals (beyond the active cap) -->
      <div v-if="backlogGoals.length > 0" class="mt-4">
        <button
          @click="showBacklogGoals = !showBacklogGoals"
          class="text-xs text-txt-muted hover:text-txt-primary transition-colors mb-2"
        >
          {{ showBacklogGoals ? 'Hide' : 'Show' }} {{ backlogGoals.length }} backlog goal{{ backlogGoals.length > 1 ? 's' : '' }}
        </button>
        <div v-if="showBacklogGoals" class="space-y-2 opacity-60">
          <div
            v-for="goal in backlogGoals"
            :key="goal.id"
            class="glass-card px-4 py-3 flex items-center gap-3"
          >
            <button
              @click="toggleGoalComplete(goal)"
              class="w-5 h-5 rounded-full border-2 border-bdr hover:border-accent flex-shrink-0"
            />
            <span class="text-sm text-txt-secondary flex-1">{{ goal.title }}</span>
            <span v-if="goal.milestone_count > 0" class="text-xs text-txt-muted">{{ goal.milestone_done }}/{{ goal.milestone_count }}</span>
            <span
              v-if="goal.deadline"
              class="text-[10px] px-1.5 py-0.5 rounded"
              :class="isOverdue(goal.deadline) ? 'bg-red-500/15 text-red-400' : 'bg-surface-3 text-txt-muted'"
            >
              {{ deadlineLabel(goal.deadline) }}
            </span>
          </div>
        </div>
        <p class="text-[10px] text-txt-muted mt-1">Focus on your top 3 active goals. Complete one to promote a backlog goal.</p>
      </div>

      <!-- Completed goals -->
      <div v-if="completedGoals.length > 0" class="mt-6">
        <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-2">Completed</p>
        <div class="space-y-2">
          <div
            v-for="goal in completedGoals"
            :key="goal.id"
            class="glass-card px-4 py-3 flex items-center gap-3 opacity-60"
          >
            <button
              @click="toggleGoalComplete(goal)"
              class="w-5 h-5 rounded-full bg-success flex items-center justify-center flex-shrink-0"
            >
              <span class="text-white text-xs">&#10003;</span>
            </button>
            <span class="text-sm text-txt-muted line-through flex-1">{{ goal.title }}</span>
            <span v-if="goal.completed_at" class="text-xs text-txt-muted">
              {{ parseUTC(goal.completed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}
            </span>
            <button
              @click="deleteGoal(goal)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-1"
            >
              &times;
            </button>
          </div>
        </div>
      </div>
    </div>
  </template>

  <!-- ===== WEEKLY TARGETS SUB-VIEW ===== -->
  <template v-if="goalSubView === 'weekly'">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-txt-primary">Weekly Targets</h2>
      <span class="text-xs text-txt-muted">This week's progress</span>
    </div>

    <!-- Set targets prompt -->
    <div v-if="weeklyTargets.length === 0" class="glass-card p-6 text-center">
      <p class="text-sm text-txt-muted mb-2">No weekly targets set yet.</p>
      <p class="text-xs text-txt-muted">
        Go to Habits &rarr; Manage to set weekly frequency targets for your habits.
      </p>
      <!-- Quick-set targets from here -->
      <div v-if="allHabits.filter(h => h.is_active).length > 0" class="mt-4 space-y-2">
        <p class="text-xs text-txt-muted font-medium">Or set targets here:</p>
        <div
          v-for="habit in allHabits.filter(h => h.is_active)"
          :key="habit.id"
          class="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2"
        >
          <component :is="getIcon(habit.emoji)" :size="20" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
          <CircleDot v-else :size="20" class="text-accent flex-shrink-0" />
          <span class="text-sm text-txt-primary flex-1">{{ habit.name }}</span>
          <template v-if="editingTargetFor === habit.id">
            <select
              v-model.number="editTargetValue"
              class="input-field w-32 text-sm"
            >
              <option :value="null">None</option>
              <option v-for="n in 7" :key="n" :value="n">{{ n }}x / week</option>
            </select>
            <button @click="setWeeklyTarget(habit.id)" class="text-xs text-accent">Save</button>
          </template>
          <button
            v-else
            @click="startEditTarget(habit)"
            class="text-xs text-accent hover:text-accent/80"
          >
            {{ habit.weekly_target ? habit.weekly_target + 'x / week' : 'Set target' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Weekly targets with progress -->
    <div v-else class="space-y-3">
      <div
        v-for="item in weeklyTargets"
        :key="item.habit_id"
        class="glass-card px-4 py-3"
      >
        <div class="flex items-center gap-3 mb-2">
          <component :is="getIcon(item.habit_emoji)" :size="22" class="text-accent flex-shrink-0" v-if="getIcon(item.habit_emoji)" />
          <CircleDot v-else :size="22" class="text-accent flex-shrink-0" />
          <div class="flex-1 min-w-0">
            <span class="text-sm font-medium text-txt-primary">{{ item.habit_name }}</span>
          </div>
          <span class="text-sm font-medium" :class="item.this_week_count >= item.weekly_target ? 'text-success' : 'text-txt-muted'">
            {{ item.this_week_count }}/{{ item.weekly_target }}
          </span>
        </div>
        <div class="w-full bg-surface-3 rounded-full h-2">
          <div
            class="h-2 rounded-full transition-[width,background-color] duration-300 ease-out"
            :class="item.progress_pct >= 100 ? 'bg-success' : 'bg-accent'"
            :style="{ width: Math.min(item.progress_pct, 100) + '%' }"
          />
        </div>
      </div>

      <!-- Also show habits without targets for easy setup -->
      <div
        v-if="allHabits.filter(h => h.is_active && !h.weekly_target).length > 0"
        class="mt-4"
      >
        <p class="text-xs text-txt-muted mb-2">Habits without targets:</p>
        <div class="space-y-1">
          <div
            v-for="habit in allHabits.filter(h => h.is_active && !h.weekly_target)"
            :key="habit.id"
            class="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2"
          >
            <component :is="getIcon(habit.emoji)" :size="18" class="text-accent flex-shrink-0" v-if="getIcon(habit.emoji)" />
            <CircleDot v-else :size="18" class="text-accent flex-shrink-0" />
            <span class="text-sm text-txt-muted flex-1">{{ habit.name }}</span>
            <template v-if="editingTargetFor === habit.id">
              <select
                v-model.number="editTargetValue"
                class="input-field w-32 text-sm"
              >
                <option :value="null">None</option>
                <option v-for="n in 7" :key="n" :value="n">{{ n }}x / week</option>
              </select>
              <button @click="setWeeklyTarget(habit.id)" class="text-xs text-accent">Save</button>
            </template>
            <button
              v-else
              @click="startEditTarget(habit)"
              class="text-xs text-accent hover:text-accent/80"
            >
              Set target
            </button>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
