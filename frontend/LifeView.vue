<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { api, ApiError, getToken } from '@core/api/client'
import { startAmbience, stopAmbience, pauseAmbience, resumeAmbience, setAmbienceVolume } from './ambience'
import { moodIcons, meditationTypeIcons, ambienceIcons, habitIcons, habitIconPicker, getIcon, BrandIcon } from './icons'
import {
  BookOpen, MessageCircleHeart, ScrollText, Send, Trash2, Pencil, X, AlertTriangle,
  LayoutDashboard, TrendingUp, Target, Clock, CalendarDays, ArrowRight, ArrowLeft,
  ChevronRight, Activity, Flame as FlameIcon, Brain as BrainIcon,
} from 'lucide-vue-next'

// --- Tabs ---

type Tab = 'dashboard' | 'journal' | 'habits' | 'goals' | 'meditate' | 'therapist'
const activeTab = ref<Tab>('dashboard')

// ============================
// DASHBOARD
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
  try {
    const res = await api.get<DashboardData>('/api/life/dashboard')
    dashboardData.value = res
  } catch (e) {
    console.error('Dashboard fetch failed:', e)
  }
}

function navigateTo(tab: Tab) {
  activeTab.value = tab
}

// Re-fetch dashboard when switching back to overview
watch(activeTab, (tab) => {
  if (tab === 'dashboard') fetchDashboard()
  // Clear stale errors when switching tabs
  journalError.value = null
  habitError.value = null
  goalError.value = null
  medError.value = null
})

// Listen for logo click → return to dashboard
function handleLogoHome() { activeTab.value = 'dashboard' }
onMounted(() => document.addEventListener('zugalife-go-home', handleLogoHome))
onUnmounted(() => document.removeEventListener('zugalife-go-home', handleLogoHome))

// Module labels for back-nav header
const moduleLabels: Record<Exclude<Tab, 'dashboard'>, string> = {
  journal: 'Journal',
  habits: 'Habits',
  goals: 'Goals',
  meditate: 'Meditate',
  therapist: 'Therapist',
}

// ============================
// MOOD DEFINITIONS (shared by journal compose)
// ============================

const moods = [
  { emoji: '😊', label: 'Happy' },
  { emoji: '😢', label: 'Sad' },
  { emoji: '😠', label: 'Angry' },
  { emoji: '😰', label: 'Anxious' },
  { emoji: '😴', label: 'Tired' },
  { emoji: '🤩', label: 'Excited' },
  { emoji: '😐', label: 'Neutral' },
  { emoji: '🥰', label: 'Loved' },
  { emoji: '😤', label: 'Frustrated' },
  { emoji: '🤔', label: 'Thoughtful' },
  { emoji: '😌', label: 'Calm' },
  { emoji: '💪', label: 'Motivated' },
]

// ============================
// JOURNAL
// ============================

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

type JournalViewState = 'list' | 'compose' | 'detail'
const journalView = ref<JournalViewState>('list')

const journalEntries = ref<JournalEntryBrief[]>([])
const totalJournalEntries = ref(0)
const loadingJournal = ref(true)

const composeTitle = ref('')
const composeContent = ref('')
const composeMood = ref<string | null>(null)
const journalSubmitting = ref(false)

const currentEntry = ref<JournalEntryFull | null>(null)
const loadingDetail = ref(false)
const reflecting = ref(false)
const reflectionsRemaining = ref(3)

const journalError = ref<string | null>(null)
const journalSuccess = ref<string | null>(null)

const contentLength = computed(() => composeContent.value.length)

const composeMoodLabel = computed(() => {
  if (!composeMood.value) return null
  return moods.find(m => m.emoji === composeMood.value)?.label ?? null
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

function goToCompose() {
  composeTitle.value = ''
  composeContent.value = ''
  composeMood.value = null
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

async function saveEntry() {
  if (!composeContent.value.trim() || journalSubmitting.value) return

  journalSubmitting.value = true
  journalError.value = null

  try {
    const res = await api.post<JournalEntryFull>('/api/life/journal', {
      title: composeTitle.value.trim() || null,
      content: composeContent.value.trim(),
      mood_emoji: composeMood.value,
    })
    journalSuccess.value = 'Journal entry saved!'
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
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      if (e.status === 402) {
        journalError.value = 'AI budget exhausted for today. Try again tomorrow.'
      } else if (e.status === 429) {
        journalError.value = body.detail ?? 'Maximum reflections reached for this entry.'
      } else {
        journalError.value = body.detail ?? `Error (${e.status})`
      }
    } else {
      journalError.value = 'Network error — is the backend running?'
    }
  } finally {
    reflecting.value = false
  }
}

async function deleteEntry() {
  if (!currentEntry.value) return

  try {
    await api.delete(`/api/life/journal/${currentEntry.value.id}`)
    journalSuccess.value = 'Entry deleted.'
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
  created_at: string
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

interface HabitInsight {
  id: number
  content: string
  model_used: string
  cost: number
  week_start: string
  created_at: string
}

interface HabitInsightListResponse {
  insights: HabitInsight[]
  total: number
}

type HabitView = 'checkin' | 'history' | 'insights' | 'manage'
const habitView = ref<HabitView>('checkin')

const habitCheckin = ref<DailyCheckInResponse | null>(null)
const habitStreaks = ref<AllStreaksResponse | null>(null)
const habitHistory = ref<HabitHistoryResponse | null>(null)
const habitInsights = ref<HabitInsight[]>([])
const allHabits = ref<HabitDefinition[]>([])
const loadingHabits = ref(true)
const habitError = ref<string | null>(null)
const habitSuccess = ref<string | null>(null)
const habitSubmitting = ref(false)
const insightGenerating = ref(false)
const historyDays = ref(7)

// New custom habit form
const newHabitName = ref('')
const newHabitIcon = ref('')  // Stores a Lucide icon name (e.g. 'dumbbell')
const newHabitUnit = ref<string | null>(null)
const newHabitTarget = ref<number | null>(null)
const showNewHabitForm = ref(false)

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

async function fetchHabitInsights() {
  try {
    const res = await api.get<HabitInsightListResponse>('/api/life/habits/insights')
    habitInsights.value = res.insights
  } catch { /* silent */ }
}

async function toggleHabit(item: HabitCheckInItem) {
  habitError.value = null
  try {
    if (item.logged) {
      // Uncheck — use local date to match server's date.today()
      const d = new Date()
      const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      await api.delete(`/api/life/habits/log/${item.habit.id}/${today}`)
    } else {
      // Check
      const amt = amountInputs.value[item.habit.id]
      await api.post('/api/life/habits/log', {
        habit_id: item.habit.id,
        completed: true,
        amount: amt ? parseFloat(amt) : null,
      })
    }
    await fetchHabitCheckin()
  } catch (e) {
    if (e instanceof ApiError) {
      habitError.value = (e.body as Record<string, string>).detail ?? `Error (${(e as ApiError).status})`
    } else {
      habitError.value = 'Network error'
    }
  }
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
      unit: newHabitUnit.value || null,
      default_target: newHabitTarget.value || null,
    })
    newHabitName.value = ''
    newHabitIcon.value = ''
    newHabitUnit.value = null
    newHabitTarget.value = null
    showNewHabitForm.value = false
    habitSuccess.value = 'Habit created!'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await Promise.all([fetchAllHabits(), fetchHabitCheckin()])
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

async function generateHabitInsight() {
  if (insightGenerating.value) return
  insightGenerating.value = true
  habitError.value = null

  try {
    await api.post('/api/life/habits/insight')
    habitSuccess.value = 'Insight generated!'
    setTimeout(() => { habitSuccess.value = null }, 2000)
    await fetchHabitInsights()
  } catch (e) {
    if (e instanceof ApiError) {
      const body = e.body as Record<string, string>
      if (e.status === 402) {
        habitError.value = 'AI budget exhausted for today. Try again tomorrow.'
      } else if (e.status === 429) {
        habitError.value = body.detail ?? 'Insight cooldown active.'
      } else if (e.status === 503) {
        habitError.value = 'AI insights not available in standalone mode.'
      } else {
        habitError.value = body.detail ?? `Error (${e.status})`
      }
    } else {
      habitError.value = 'Network error'
    }
  } finally {
    insightGenerating.value = false
  }
}

const habitUnits = [
  { value: 'hours', label: 'Hours' },
  { value: 'minutes', label: 'Minutes' },
  { value: 'glasses', label: 'Glasses' },
  { value: 'steps', label: 'Steps' },
  { value: 'servings', label: 'Servings' },
  { value: 'pages', label: 'Pages' },
  { value: 'count', label: 'Count' },
]

// ============================
// GOALS
// ============================

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

type GoalSubView = 'goals' | 'weekly'
const goalSubView = ref<GoalSubView>('goals')

const activeGoals = ref<Goal[]>([])
const completedGoals = ref<Goal[]>([])
const weeklyTargets = ref<WeeklyTargetItem[]>([])
const loadingGoals = ref(true)
const goalError = ref<string | null>(null)
const goalSuccess = ref<string | null>(null)

// Create goal form
type GoalCreateMode = 'none' | 'templates' | 'custom'
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

// Editing weekly target
const editingTargetFor = ref<number | null>(null)
const editTargetValue = ref<number | null>(null)

function toggleGoalExpand(id: number) {
  if (expandedGoals.value.has(id)) {
    expandedGoals.value.delete(id)
  } else {
    expandedGoals.value.add(id)
  }
}

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

async function linkHabit(goalId: number, habitId: number) {
  goalError.value = null
  try {
    await api.post(`/api/life/goals/${goalId}/habits`, { habit_id: habitId })
    linkingHabitTo.value = null
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

async function unlinkHabit(goalId: number, habitId: number) {
  goalError.value = null
  try {
    await api.delete(`/api/life/goals/${goalId}/habits/${habitId}`)
    await fetchGoals()
  } catch (e) {
    if (e instanceof ApiError) {
      goalError.value = (e.body as Record<string, string>).detail ?? `Error (${e.status})`
    } else {
      goalError.value = 'Network error'
    }
  }
}

function availableHabitsForGoal(goal: Goal): HabitDefinition[] {
  const linkedIds = new Set(goal.linked_habits.map(h => h.habit_id))
  return allHabits.value.filter(h => h.is_active && !linkedIds.has(h.id))
}

async function fetchWeeklyTargets() {
  try {
    const res = await api.get<WeeklyTargetsResponse>('/api/life/habits/weekly')
    weeklyTargets.value = res.habits
  } catch { /* silent */ }
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
  try {
    await api.delete(`/api/life/goals/${goal.id}`)
    goalSuccess.value = 'Goal deleted.'
    setTimeout(() => { goalSuccess.value = null }, 2000)
    await fetchGoals()
  } catch (e) {
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
  try {
    await api.patch(`/api/life/goals/${goalId}/milestones/${milestone.id}`, {
      is_completed: !milestone.is_completed,
    })
    await fetchGoals()
  } catch (e) {
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

// ============================
// MEDITATION
// ============================

interface MeditationSession {
  id: number
  type: string
  duration_minutes: number
  ambience: string
  voice: string
  focus: string | null
  title: string
  transcript: string
  audio_filename: string
  model_used: string
  tts_model: string
  cost: number
  mood_before: string | null
  mood_after: string | null
  is_favorite: boolean
  created_at: string
}

interface MeditationBrief {
  id: number
  type: string
  duration_minutes: number
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

const durationOptions = [3, 5, 10, 15]

type MedView = 'new' | 'player' | 'history'
const medView = ref<MedView>('new')

// Config state
const medType = ref('breathing')
const medDuration = ref(5)
const medAmbience = ref('rain')
const medVoice = ref('shimmer')
const medFocus = ref('')

// Generation
const medGenerating = ref(false)
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

const transcriptParagraphs = computed(() => {
  if (!medSession.value) return []
  return medSession.value.transcript
    .replace(/\[PAUSE\s*\d+s?\]/g, '')
    .split('\n\n')
    .map(p => p.trim())
    .filter(p => p.length > 0)
})

const activeParagraphIndex = computed(() => {
  if (!transcriptParagraphs.value.length) return 0
  const idx = Math.floor((medProgress.value / 100) * transcriptParagraphs.value.length)
  return Math.min(idx, transcriptParagraphs.value.length - 1)
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

async function generateMeditation() {
  if (medGenerating.value) return
  medGenerating.value = true
  medError.value = null

  try {
    const payload: Record<string, unknown> = {
      type: medType.value,
      duration_minutes: medDuration.value,
      ambience: medAmbience.value,
      voice: medVoice.value,
    }
    if (medFocus.value.trim()) {
      payload.focus = medFocus.value.trim()
    }

    medSession.value = await api.post<MeditationSession>('/api/life/meditation/generate', payload)
    medMoodAfter.value = null
    medView.value = 'player'
    medSuccess.value = 'Meditation generated!'
    setTimeout(() => { medSuccess.value = null }, 2000)
    await fetchMedRemaining()
    await fetchMedSessions()
    setTimeout(() => loadAndPlayAudio(), 300)
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 402) {
        medError.value = 'AI budget exhausted for today.'
      } else if (e.status === 429) {
        medError.value = detail ?? 'Daily meditation limit reached.'
      } else if (e.status === 503) {
        medError.value = 'Meditation generation not available.'
      } else {
        medError.value = detail ?? `Error (${e.status})`
      }
    } else {
      medError.value = 'Network error'
    }
  } finally {
    medGenerating.value = false
  }
}

let medAudioLoading = false

async function loadAndPlayAudio() {
  if (!medSession.value || medAudioLoading) return
  medAudioLoading = true
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
    audio.addEventListener('ended', () => {
      medPlaying.value = false
      medProgress.value = 100
      stopAmbient()
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
// SHARED HELPERS
// ============================

/** Ensure ISO timestamps are treated as UTC (backend omits Z suffix) */
function parseUTC(iso: string): Date {
  return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
}

function timeAgo(iso: string): string {
  const diff = Date.now() - parseUTC(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDate(iso: string): string {
  return parseUTC(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function formatDashboardDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  })
}

function formatDeadline(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const now = new Date()
  const diff = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diff < 0) return 'overdue'
  if (diff === 0) return 'today'
  if (diff === 1) return 'tomorrow'
  if (diff <= 7) return `${diff} days`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// ============================
// THERAPIST
// ============================

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
const therapistView = ref<TherapistView>('chat')

const therapistMessages = ref<TherapistMessage[]>([])
const therapistInput = ref('')
const therapistSending = ref(false)
const therapistGreeting = ref('')
const therapistDisclaimer = "I'm an AI companion, not a licensed therapist. I draw from psychology, philosophy, and contemplative traditions to help you reflect. I make mistakes \u2014 please push back when something doesn't feel right. For crisis support, call 988 or text HOME to 741741."
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
const therapistEditThemes = ref('')
const therapistEditPatterns = ref('')
const therapistEditFollowUp = ref('')

const therapistMessagesRemaining = ref(20)

const chatContainer = ref<HTMLElement | null>(null)

watch(therapistMessages, () => {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}, { deep: true })

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
    // disclaimer is hardcoded in frontend — no need to fetch
  } catch {
    therapistGreeting.value = ''
  }
}

async function fetchTherapistNotes() {
  try {
    const res = await api.get<{ notes: TherapistSessionNote[]; total: number }>('/api/life/therapist/notes')
    therapistNotes.value = res.notes
  } catch { /* silent */ }
}

async function startTherapistSession() {
  therapistMessages.value = []
  therapistSessionActive.value = true
  therapistError.value = null
  therapistMessagesRemaining.value = 20
  therapistSending.value = true

  // Fetch greeting on demand if not already loaded
  if (!therapistGreeting.value) {
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
    therapistMessagesRemaining.value = res.session_messages_remaining

    // Auto-end session when limit reached (therapist already wrapped up naturally)
    if (res.session_messages_remaining <= 0) {
      therapistSending.value = false
      await endTherapistSession()
      return
    }
  } catch (e) {
    if (e instanceof ApiError) {
      const detail = (e.body as Record<string, string>).detail
      if (e.status === 429) {
        therapistError.value = detail ?? 'Session limit reached for today.'
      } else if (e.status === 503) {
        therapistError.value = 'Therapist unavailable — Venice may be down.'
        therapistAvailable.value = false
      } else {
        therapistError.value = detail ?? `Error (${e.status})`
      }
    } else {
      therapistError.value = 'Network error — is the backend running?'
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
  therapistEndingSession.value = true
  therapistError.value = null

  try {
    const apiMessages = therapistMessages.value.map(m => ({ role: m.role, content: m.content }))
    await api.post('/api/life/therapist/end-session', { messages: apiMessages })
    therapistSuccess.value = 'Session saved!'
    setTimeout(() => { therapistSuccess.value = null }, 3000)
    therapistSessionActive.value = false
    therapistMessages.value = []
    await fetchTherapistStatus()
    await fetchTherapistGreeting()
    await fetchTherapistNotes()
  } catch (e) {
    if (e instanceof ApiError) {
      therapistError.value = (e.body as Record<string, string>).detail ?? 'Failed to save session.'
    } else {
      therapistError.value = 'Network error'
    }
  } finally {
    therapistEndingSession.value = false
  }
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

// --- Init ---

onMounted(async () => {
  await Promise.all([
    fetchDashboard(),
    fetchJournalEntries(),
    fetchHabitCheckin(), fetchHabitStreaks(), fetchAllHabits(),
    fetchGoals(), fetchGoalTemplates(), fetchWeeklyTargets(),
    fetchMedRemaining(), fetchMedSessions(),
    fetchTherapistStatus(), fetchTherapistNotes(),
  ])
  loadingDashboard.value = false
  loadingJournal.value = false
  loadingHabits.value = false
  loadingGoals.value = false
  loadingMeditation.value = false
  loadingTherapist.value = false
  // Greeting fetched on-demand in startTherapistSession() — don't block page load
})

onUnmounted(() => {
  stopAudio()
})
</script>

<template>
  <div
    class="max-w-2xl mx-auto py-10 animate-fade-in"
    :class="activeTab !== 'dashboard'
      ? 'px-6 mx-4 sm:mx-auto rounded-2xl bg-surface-0/70 backdrop-blur-xl border border-white/[0.04]'
      : 'px-6'"
  >

    <!-- Success Toasts -->
    <transition name="fade">
      <div
        v-if="journalSuccess || habitSuccess || goalSuccess || medSuccess || therapistSuccess"
        class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-6 py-3 rounded-lg bg-emerald-600 text-white font-medium text-sm shadow-lg"
      >
        {{ journalSuccess || habitSuccess || goalSuccess || medSuccess || therapistSuccess }}
      </div>
    </transition>

    <!-- Back nav + module label (shown on non-dashboard tabs) -->
    <div v-if="activeTab !== 'dashboard'" class="flex items-center gap-3 mb-6">
      <button
        @click="activeTab = 'dashboard'"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-txt-muted transition-colors hover:text-txt-primary hover:bg-surface-3/50"
      >
        <ArrowLeft :size="16" />
        <span>Back</span>
      </button>
      <span class="text-sm font-semibold text-txt-primary">{{ moduleLabels[activeTab] }}</span>
      <div class="flex-1" />
      <div
        v-if="habitStreaks && habitStreaks.overall_current > 0"
        class="flex items-center gap-1.5 text-sm text-txt-secondary"
      >
        <FlameIcon :size="14" class="text-amber-400" />
        <span class="font-medium">{{ habitStreaks.overall_current }}-day streak</span>
      </div>
    </div>

    <!-- ===== DASHBOARD TAB ===== -->
    <template v-if="activeTab === 'dashboard'">
      <div v-if="loadingDashboard" class="flex items-center justify-center py-20">
        <div class="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
      </div>

      <template v-else-if="dashboardData">
        <!-- Greeting -->
        <div class="mb-8 animate-fade-in inline-block px-5 py-3 rounded-2xl bg-surface-0/60 backdrop-blur-md">
          <p class="text-sm text-txt-muted mb-1">{{ formatDashboardDate(dashboardData.date) }}</p>
          <h2 class="text-2xl font-bold text-txt-primary tracking-tight">{{ dashboardData.greeting }}</h2>
          <p class="text-sm text-txt-secondary mt-1.5">Here's your week at a glance.</p>
        </div>

        <!-- Metric Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">

          <!-- HABITS CARD -->
          <button
            @click="navigateTo('habits')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group"
            style="animation-delay: 50ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <TrendingUp :size="18" class="text-emerald-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Habits</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
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
                    :class="dashboardData.habits.completion_rate >= 0.8 ? 'bg-emerald-500' : dashboardData.habits.completion_rate >= 0.5 ? 'bg-amber-500' : 'bg-surface-4'"
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
            @click="navigateTo('goals')"
            class="dash-card glass-card p-5 text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group"
            style="animation-delay: 100ms"
          >
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-xl bg-sky-500/10 flex items-center justify-center">
                  <Target :size="18" class="text-sky-400" />
                </div>
                <span class="text-sm font-semibold text-txt-primary">Goals</span>
              </div>
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
            <template v-if="dashboardData.goals.has_data">
              <div class="flex items-baseline gap-4 mb-3">
                <div>
                  <span class="text-2xl font-bold text-txt-primary">{{ dashboardData.goals.active }}</span>
                  <span class="text-xs text-txt-muted ml-1">active</span>
                </div>
                <div v-if="dashboardData.goals.completed > 0">
                  <span class="text-lg font-semibold text-emerald-400">{{ dashboardData.goals.completed }}</span>
                  <span class="text-xs text-txt-muted ml-1">done</span>
                </div>
              </div>
              <div v-if="dashboardData.goals.milestones_total > 0" class="mb-2">
                <div class="flex items-center justify-between text-xs text-txt-muted mb-1">
                  <span>Milestones</span>
                  <span>{{ dashboardData.goals.milestones_done }}/{{ dashboardData.goals.milestones_total }}</span>
                </div>
                <div class="w-full bg-surface-3 rounded-full h-1.5">
                  <div
                    class="h-1.5 rounded-full bg-sky-500 transition-all duration-500"
                    :style="{ width: Math.round((dashboardData.goals.milestones_done / dashboardData.goals.milestones_total) * 100) + '%' }"
                  ></div>
                </div>
              </div>
              <div v-if="dashboardData.goals.nearest_deadline" class="flex items-center gap-1.5 text-xs text-txt-muted">
                <CalendarDays :size="12" />
                <span>{{ dashboardData.goals.nearest_deadline.title }}</span>
                <span class="text-txt-muted">·</span>
                <span>{{ formatDeadline(dashboardData.goals.nearest_deadline.date) }}</span>
              </div>
            </template>
            <template v-else>
              <p class="text-sm text-txt-muted">Set meaningful goals</p>
              <p class="text-xs text-txt-muted mt-1">Choose from templates or create your own</p>
            </template>
          </button>

          <!-- MEDITATION CARD -->
          <button
            @click="navigateTo('meditate')"
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
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
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
            @click="navigateTo('journal')"
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
              <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
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
                  <component :is="moodIcons[entry.emoji]" :size="14" class="text-amber-400" v-if="moodIcons[entry.emoji]" />
                  <span v-else class="text-xs">{{ entry.emoji }}</span>
                </div>
              </template>
              <span class="text-xs text-txt-muted ml-1">recent moods</span>
            </div>
          </button>
        </div>

        <!-- Therapist card — full width hero CTA -->
        <button
          @click="navigateTo('therapist')"
          class="dash-card glass-card p-5 w-full text-left transition-all duration-200 hover:bg-surface-2 hover:border-bdr-hover group"
          style="animation-delay: 250ms"
        >
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2.5">
              <div class="w-9 h-9 rounded-xl bg-teal-500/10 flex items-center justify-center">
                <MessageCircleHeart :size="18" class="text-teal-400" />
              </div>
              <span class="text-sm font-semibold text-txt-primary">Therapist</span>
            </div>
            <ChevronRight :size="16" class="text-txt-muted opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          <template v-if="dashboardData.therapist.has_data">
            <p class="text-sm text-txt-secondary mb-2 line-clamp-1">{{ dashboardData.therapist.last_themes }}</p>
            <div class="flex items-center gap-2 text-xs text-txt-muted">
              <span v-if="dashboardData.therapist.last_mood" class="px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400">{{ dashboardData.therapist.last_mood }}</span>
              <span>{{ dashboardData.therapist.total_sessions }} sessions</span>
              <span v-if="dashboardData.therapist.last_date">· {{ timeAgo(dashboardData.therapist.last_date) }}</span>
            </div>
          </template>
          <template v-else>
            <p class="text-sm text-txt-muted">AI companion for reflection — talk through what's on your mind</p>
          </template>
        </button>

        <!-- Streak banner (if exists) -->
        <div
          v-if="habitStreaks && habitStreaks.overall_current > 0"
          class="mt-6 glass-card p-4 flex items-center gap-3 border-amber-500/20"
        >
          <div class="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
            <FlameIcon :size="20" class="text-amber-400" />
          </div>
          <div class="flex-1">
            <p class="text-sm font-semibold text-txt-primary">{{ habitStreaks.overall_current }}-day streak</p>
            <p class="text-xs text-txt-muted">Keep it going! Best: {{ habitStreaks.overall_longest }} days</p>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== HABITS TAB ===== -->
    <template v-if="activeTab === 'habits'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'checkin', label: 'Check-in' },
            { key: 'history', label: 'History' },
            { key: 'insights', label: 'Insights' },
            { key: 'manage', label: 'Manage' },
          ] as { key: HabitView; label: string }[]"
          :key="view.key"
          @click="habitView = view.key; if (view.key === 'history') fetchHabitHistory(); if (view.key === 'insights') fetchHabitInsights()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
          :class="habitView === view.key ? 'bg-accent/15 text-accent' : 'text-txt-muted hover:text-txt-primary hover:bg-surface-3'"
        >
          {{ view.label }}
        </button>
      </div>

      <p v-if="habitError" class="text-sm text-red-400 mb-4">{{ habitError }}</p>

      <!-- ===== CHECK-IN VIEW ===== -->
      <template v-if="habitView === 'checkin'">
        <div v-if="loadingHabits" class="text-sm text-txt-muted">Loading habits...</div>
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
                class="h-2.5 rounded-full transition-all duration-500"
                :class="completionPercent === 100 ? 'bg-emerald-500' : 'bg-accent'"
                :style="{ width: completionPercent + '%' }"
              />
            </div>
          </div>

          <!-- Habit cards -->
          <div class="space-y-2">
            <div
              v-for="item in habitCheckin.habits"
              :key="item.habit.id"
              class="glass-card px-4 py-3 flex items-center gap-3 transition-all duration-200"
              :class="item.logged ? 'ring-1 ring-emerald-500/30' : ''"
            >
              <button
                @click="toggleHabit(item)"
                class="w-6 h-6 rounded-md border-2 flex items-center justify-center transition-all flex-shrink-0"
                :class="item.logged
                  ? 'bg-emerald-500 border-emerald-500 text-white'
                  : 'border-bdr hover:border-accent'"
              >
                <span v-if="item.logged" class="text-xs">&#10003;</span>
              </button>
              <component :is="getIcon(item.habit.emoji)" :size="22" class="flex-shrink-0 text-accent" v-if="getIcon(item.habit.emoji)" />
              <span v-else class="text-xl flex-shrink-0">{{ item.habit.emoji }}</span>
              <div class="flex-1 min-w-0">
                <span class="text-sm font-medium text-txt-primary">{{ item.habit.name }}</span>
              </div>
              <div v-if="item.habit.unit" class="flex items-center gap-1.5">
                <input
                  type="number"
                  :value="amountInputs[item.habit.id] ?? ''"
                  @input="amountInputs[item.habit.id] = ($event.target as HTMLInputElement).value"
                  @blur="updateHabitAmount(item)"
                  @keyup.enter="updateHabitAmount(item)"
                  :placeholder="item.habit.default_target ? String(item.habit.default_target) : '0'"
                  class="w-16 px-2 py-1 text-sm text-right rounded-md bg-surface-3 text-txt-primary border border-bdr focus:border-accent focus:outline-none"
                />
                <span class="text-xs text-txt-muted">{{ item.habit.unit }}</span>
              </div>
            </div>
          </div>

          <!-- Streaks summary -->
          <div v-if="habitStreaks && habitStreaks.overall_current > 0" class="glass-card p-4 mt-6 flex items-center gap-3">
            <span class="text-lg">&#x1F525;</span>
            <div>
              <p class="text-sm font-semibold text-txt-primary">{{ habitStreaks.overall_current }}-day habit streak</p>
              <p class="text-xs text-txt-muted">Longest: {{ habitStreaks.overall_longest }} days</p>
            </div>
          </div>

          <!-- Reset options -->
          <div class="mt-6 flex flex-wrap gap-2">
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
              class="px-3 py-1 text-xs rounded-lg transition-colors"
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
                :class="day.completion_rate >= 1 ? 'bg-emerald-500' : day.completion_rate > 0 ? 'bg-accent' : 'bg-surface-3'"
                :style="{ width: Math.round(day.completion_rate * 100) + '%' }"
              />
            </div>
            <div v-if="day.habits_done.length > 0" class="flex gap-1 flex-wrap">
              <template v-for="(emoji, i) in day.habits_done" :key="i">
                <component :is="getIcon(emoji)" :size="14" class="text-accent" v-if="getIcon(emoji)" />
                <span v-else class="text-sm">{{ emoji }}</span>
              </template>
            </div>
          </div>
        </div>
      </template>

      <!-- ===== INSIGHTS VIEW ===== -->
      <template v-if="habitView === 'insights'">
        <div class="mb-6">
          <button
            @click="generateHabitInsight"
            :disabled="insightGenerating"
            class="btn-primary w-full"
          >
            <span v-if="insightGenerating" class="inline-flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Analyzing patterns...
            </span>
            <span v-else>Get Weekly Insight</span>
          </button>
          <p class="text-xs text-txt-muted text-center mt-2">Correlates your habits with mood data (7-day cooldown)</p>
        </div>
        <div v-if="habitInsights.length === 0" class="glass-card p-6 text-center">
          <p class="text-txt-muted text-sm">No insights yet. Generate your first weekly analysis!</p>
        </div>
        <div v-else class="space-y-3">
          <div v-for="insight in habitInsights" :key="insight.id" class="glass-card p-4 animate-slide-up">
            <div class="flex items-center gap-2 mb-2">
              <span class="text-xs font-medium text-accent">Week of {{ new Date(insight.week_start + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}</span>
              <span class="text-xs text-txt-muted">{{ formatDate(insight.created_at) }}</span>
              <span class="text-xs text-txt-muted ml-auto">${{ insight.cost.toFixed(4) }}</span>
            </div>
            <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ insight.content }}</p>
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
          </div>
          <div class="flex gap-2">
            <select
              v-model="newHabitUnit"
              class="input-field flex-1 text-sm"
            >
              <option :value="null">No unit (checkbox)</option>
              <option v-for="u in habitUnits" :key="u.value" :value="u.value">{{ u.label }}</option>
            </select>
            <input
              v-if="newHabitUnit"
              v-model.number="newHabitTarget"
              type="number"
              placeholder="Target"
              min="1"
              class="input-field w-24 text-sm"
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
            <span v-else class="text-xl">{{ habit.emoji }}</span>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-txt-primary">{{ habit.name }}</span>
              <div class="flex items-center gap-2">
                <span v-if="habit.unit" class="text-xs text-txt-muted">{{ habit.default_target }} {{ habit.unit }}</span>
                <span v-if="habit.is_preset" class="text-xs text-txt-muted">(preset)</span>
              </div>
            </div>
            <button
              @click="toggleHabitActive(habit)"
              class="text-xs px-2 py-1 rounded transition-colors"
              :class="habit.is_active ? 'text-amber-400 hover:bg-amber-400/10' : 'text-emerald-400 hover:bg-emerald-400/10'"
            >
              {{ habit.is_active ? 'Deactivate' : 'Activate' }}
            </button>
            <button
              v-if="resettingHabit !== habit.id"
              @click="resettingHabit = habit.id"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1"
            >
              Reset
            </button>
            <div v-else class="flex items-center gap-1 animate-fade-in">
              <button @click="resetSingleHabit(habit.id)" class="text-xs text-red-400 hover:text-red-300 font-medium px-1">Clear logs</button>
              <button @click="resettingHabit = null" class="text-xs text-txt-muted hover:text-txt-primary px-1">Cancel</button>
            </div>
            <button
              v-if="!habit.is_preset"
              @click="deleteCustomHabit(habit)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1"
            >
              Delete
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== GOALS TAB ===== -->
    <template v-if="activeTab === 'goals'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'goals', label: 'Life Goals' },
            { key: 'weekly', label: 'Weekly Targets' },
          ] as { key: GoalSubView; label: string }[]"
          :key="view.key"
          @click="goalSubView = view.key; if (view.key === 'weekly') fetchWeeklyTargets()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
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
          <div class="text-center">
            <button
              @click="goalCreateMode = 'custom'"
              class="text-xs text-txt-muted hover:text-accent transition-colors"
            >
              Or create a custom goal &rarr;
            </button>
          </div>
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
              &larr; Templates
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

        <!-- Active goals -->
        <div v-else class="space-y-3">
          <div
            v-for="goal in activeGoals"
            :key="goal.id"
            class="glass-card overflow-hidden animate-slide-up"
          >
            <!-- Goal header -->
            <div class="px-4 py-3 flex items-start gap-3">
              <button
                @click="toggleGoalComplete(goal)"
                class="w-5 h-5 rounded-full border-2 border-bdr hover:border-accent flex-shrink-0 mt-0.5 transition-colors"
              />
              <div class="flex-1 min-w-0 cursor-pointer" @click="toggleGoalExpand(goal.id)">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-txt-primary">{{ goal.title }}</span>
                  <span
                    v-if="goal.deadline"
                    class="text-xs px-1.5 py-0.5 rounded"
                    :class="isOverdue(goal.deadline) ? 'bg-red-500/15 text-red-400' : 'bg-surface-3 text-txt-muted'"
                  >
                    {{ new Date(goal.deadline + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}
                  </span>
                </div>
                <p v-if="goal.description" class="text-xs text-txt-muted mt-1 line-clamp-2">{{ goal.description }}</p>
                <!-- Milestone progress bar -->
                <div v-if="goal.milestone_count > 0" class="mt-2">
                  <div class="flex items-center justify-between mb-1">
                    <span class="text-xs text-txt-muted">{{ goal.milestone_done }}/{{ goal.milestone_count }} milestones</span>
                    <span class="text-xs text-txt-muted">{{ goalMilestonePct(goal) }}%</span>
                  </div>
                  <div class="w-full bg-surface-3 rounded-full h-1.5">
                    <div
                      class="h-1.5 rounded-full transition-all duration-500"
                      :class="goalMilestonePct(goal) === 100 ? 'bg-emerald-500' : 'bg-accent'"
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

              <!-- Linked habits -->
              <div v-if="goal.linked_habits.length > 0" class="space-y-1.5">
                <p class="text-xs font-semibold text-txt-muted uppercase tracking-wide">Linked Habits</p>
                <div v-for="lh in goal.linked_habits" :key="lh.habit_id" class="flex items-center gap-2 group">
                  <component :is="getIcon(lh.habit_emoji)" :size="16" class="text-accent flex-shrink-0" v-if="getIcon(lh.habit_emoji)" />
                  <span v-else class="text-sm">{{ lh.habit_emoji }}</span>
                  <span class="text-sm text-txt-primary flex-1">{{ lh.habit_name }}</span>
                  <div class="flex gap-0.5">
                    <div
                      v-for="d in lh.days_total"
                      :key="d"
                      class="w-3 h-3 rounded-sm"
                      :class="d <= lh.days_completed ? 'bg-emerald-500' : 'bg-surface-3'"
                    />
                  </div>
                  <span class="text-xs text-txt-muted w-8 text-right">{{ lh.days_completed }}/{{ lh.days_total }}</span>
                  <button
                    @click="unlinkHabit(goal.id, lh.habit_id)"
                    class="text-xs text-txt-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 px-1"
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
                    <component :is="getIcon(h.emoji)" :size="14" class="inline-block" v-if="getIcon(h.emoji)" /><span v-else>{{ h.emoji }}</span> {{ h.name }}
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
                    class="w-4 h-4 rounded border flex items-center justify-center transition-all flex-shrink-0"
                    :class="ms.is_completed
                      ? 'bg-emerald-500 border-emerald-500 text-white'
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
                    class="text-xs text-txt-muted hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 px-1"
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
                  @click="deleteGoal(goal)"
                  class="text-xs text-txt-muted hover:text-red-400 transition-colors ml-auto"
                >
                  Delete Goal
                </button>
              </div>
            </div>
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
                  class="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center flex-shrink-0"
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
              <span v-else class="text-lg">{{ habit.emoji }}</span>
              <span class="text-sm text-txt-primary flex-1">{{ habit.name }}</span>
              <template v-if="editingTargetFor === habit.id">
                <select
                  v-model.number="editTargetValue"
                  class="input-field w-20 text-sm"
                >
                  <option :value="null">None</option>
                  <option v-for="n in 7" :key="n" :value="n">{{ n }}x/wk</option>
                </select>
                <button @click="setWeeklyTarget(habit.id)" class="text-xs text-accent">Save</button>
              </template>
              <button
                v-else
                @click="startEditTarget(habit)"
                class="text-xs text-accent hover:text-accent/80"
              >
                {{ habit.weekly_target ? habit.weekly_target + 'x/wk' : 'Set target' }}
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
              <span v-else class="text-xl">{{ item.habit_emoji }}</span>
              <div class="flex-1 min-w-0">
                <span class="text-sm font-medium text-txt-primary">{{ item.habit_name }}</span>
              </div>
              <span class="text-sm font-medium" :class="item.this_week_count >= item.weekly_target ? 'text-emerald-400' : 'text-txt-muted'">
                {{ item.this_week_count }}/{{ item.weekly_target }}
              </span>
            </div>
            <div class="w-full bg-surface-3 rounded-full h-2">
              <div
                class="h-2 rounded-full transition-all duration-500"
                :class="item.progress_pct >= 100 ? 'bg-emerald-500' : 'bg-accent'"
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
                <span v-else>{{ habit.emoji }}</span>
                <span class="text-sm text-txt-muted flex-1">{{ habit.name }}</span>
                <template v-if="editingTargetFor === habit.id">
                  <select
                    v-model.number="editTargetValue"
                    class="input-field w-20 text-sm"
                  >
                    <option :value="null">None</option>
                    <option v-for="n in 7" :key="n" :value="n">{{ n }}x/wk</option>
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

    <!-- ===== MEDITATE TAB ===== -->
    <template v-if="activeTab === 'meditate'">
      <!-- Sub-nav -->
      <div class="flex gap-3 mb-6">
        <button
          v-for="view in [
            { key: 'new', label: 'New Session' },
            { key: 'history', label: 'History' },
          ] as { key: MedView; label: string }[]"
          :key="view.key"
          @click="medView = view.key; if (view.key === 'history') fetchMedSessions()"
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
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

      <!-- ===== NEW SESSION VIEW ===== -->
      <template v-if="medView === 'new'">
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

        <!-- Duration -->
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-txt-primary mb-3">Duration</h3>
          <div class="flex gap-2">
            <button
              v-for="d in durationOptions"
              :key="d"
              @click="medDuration = d"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medDuration === d
                ? 'bg-accent text-white'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              ~{{ d }} min
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
              @click="medVoice = 'shimmer'"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medVoice === 'shimmer'
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              Shimmer
              <span class="block text-xs opacity-70">Warm &amp; gentle</span>
            </button>
            <button
              @click="medVoice = 'nova'"
              class="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              :class="medVoice === 'nova'
                ? 'bg-accent/15 ring-1 ring-accent/50 text-accent'
                : 'glass-card text-txt-muted hover:text-txt-primary'"
            >
              Nova
              <span class="block text-xs opacity-70">Clear &amp; bright</span>
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

        <!-- Generate button -->
        <button
          @click="generateMeditation"
          :disabled="medGenerating || (medRemaining && medRemaining.remaining <= 0)"
          class="btn-primary w-full py-3"
        >
          <span v-if="medGenerating" class="inline-flex items-center gap-2">
            <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            Generating your meditation...
          </span>
          <span v-else-if="medRemaining && medRemaining.remaining <= 0">
            No sessions remaining today
          </span>
          <span v-else>Generate Meditation</span>
        </button>
        <p v-if="medGenerating" class="text-xs text-txt-muted text-center mt-2">This takes 15-30 seconds (AI script + voice synthesis)</p>
      </template>

      <!-- ===== PLAYER VIEW ===== -->
      <template v-if="medView === 'player' && medSession">
        <!-- Back button -->
        <button @click="goToNewMeditation" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-4">&larr; New session</button>

        <!-- Session card -->
        <div class="glass-card p-6 mb-4">
          <div class="flex items-start justify-between mb-3">
            <div>
              <h2 class="text-lg font-semibold text-txt-primary">{{ medSession.title }}</h2>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs text-txt-muted">{{ getMedTypeLabel(medSession.type) }}</span>
                <span class="text-xs text-txt-muted">~{{ medSession.duration_minutes }} min</span>
                <span class="text-xs text-txt-muted">${{ medSession.cost.toFixed(4) }}</span>
              </div>
            </div>
            <button
              @click="toggleMedFavorite"
              class="text-xl transition-colors"
              :class="medSession.is_favorite ? 'text-amber-400' : 'text-txt-muted hover:text-amber-400'"
            >
              {{ medSession.is_favorite ? '&#9733;' : '&#9734;' }}
            </button>
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
        <div class="glass-card p-5 mb-4 max-h-64 overflow-y-auto">
          <h3 class="text-xs font-semibold text-txt-muted uppercase tracking-wide mb-3">Transcript</h3>
          <div class="space-y-3">
            <p
              v-for="(para, i) in transcriptParagraphs"
              :key="i"
              class="text-sm leading-relaxed transition-all duration-500"
              :class="i <= activeParagraphIndex
                ? 'text-txt-secondary'
                : 'text-txt-muted/40'"
            >
              {{ para }}
            </p>
          </div>
        </div>

        <!-- Post-session mood (show when audio ends) -->
        <div v-if="medProgress >= 100" class="glass-card p-5 animate-fade-in">
          <h3 class="text-sm font-semibold text-txt-primary mb-2">How do you feel?</h3>
          <p class="text-xs text-txt-muted mb-3">Optional post-session check-in</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="mood in moods"
              :key="mood.emoji"
              @click="setMedMoodAfter(mood.emoji)"
              class="w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150"
              :class="medMoodAfter === mood.emoji ? 'bg-accent/15 ring-1 ring-accent/50 text-accent' : 'text-txt-muted hover:bg-surface-3 hover:text-txt-primary'"
              :title="mood.label"
            >
              <component :is="moodIcons[mood.emoji]" :size="20" v-if="moodIcons[mood.emoji]" />
            </button>
          </div>
          <p v-if="medMoodAfter" class="text-xs text-accent mt-2 animate-fade-in">
            {{ moods.find(m => m.emoji === medMoodAfter)?.label ?? '' }}
          </p>
        </div>
      </template>

      <!-- ===== HISTORY VIEW ===== -->
      <template v-if="medView === 'history'">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-txt-primary">Past Sessions</h2>
          <button
            @click="medShowFavoritesOnly = !medShowFavoritesOnly"
            class="text-sm transition-colors"
            :class="medShowFavoritesOnly ? 'text-amber-400' : 'text-txt-muted hover:text-txt-primary'"
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
            <span class="text-2xl flex-shrink-0">{{ getMedTypeEmoji(s.type) }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium text-txt-primary truncate">{{ s.title }}</span>
                <span class="text-xs text-txt-muted flex-shrink-0">{{ timeAgo(s.created_at) }}</span>
              </div>
              <div class="flex items-center gap-2 mt-0.5">
                <span class="text-xs text-txt-muted">{{ getMedTypeLabel(s.type) }}</span>
                <span class="text-xs text-txt-muted">~{{ s.duration_minutes }} min</span>
                <span v-if="s.mood_after" class="text-sm">{{ s.mood_after }}</span>
                <span v-if="s.is_favorite" class="text-amber-400 text-xs">&#9733;</span>
              </div>
            </div>
            <button
              @click.stop="deleteMedSession(s.id)"
              class="text-xs text-txt-muted hover:text-red-400 transition-colors px-1 self-center"
            >
              &times;
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- ===== THERAPIST TAB ===== -->
    <template v-if="activeTab === 'therapist'">
      <!-- Unavailable state -->
      <div v-if="!therapistAvailable" class="glass-card p-8 text-center">
        <AlertTriangle :size="32" class="mx-auto mb-3 text-amber-400" />
        <h3 class="text-lg font-semibold text-txt-primary mb-2">Therapist Unavailable</h3>
        <p class="text-sm text-txt-muted">Venice AI is currently unreachable. Please try again later.</p>
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
            class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors"
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
            <div v-if="therapistDisclaimer" class="glass-card p-4 border border-amber-500/20">
              <div class="flex items-start gap-2">
                <AlertTriangle :size="16" class="text-amber-400 mt-0.5 shrink-0" />
                <p class="text-xs text-txt-muted leading-relaxed">{{ therapistDisclaimer }}</p>
              </div>
            </div>

            <div class="glass-card p-8 text-center">
              <MessageCircleHeart :size="40" class="mx-auto mb-4 text-accent" />
              <h3 class="text-lg font-semibold text-txt-primary mb-2">Ready to talk?</h3>
              <p class="text-sm text-txt-muted mb-6 max-w-md mx-auto">
                A private space to reflect, process, and explore what's on your mind.
                Powered by Venice AI — your data stays private.
              </p>
              <button
                @click="startTherapistSession()"
                :disabled="therapistStatus?.sessions_remaining === 0"
                class="px-6 py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {{ therapistStatus?.sessions_remaining === 0 ? 'No sessions left today' : 'Start Session' }}
              </button>
            </div>
          </div>

          <!-- Active session: chat -->
          <div v-else class="flex flex-col" style="height: calc(100vh - 300px); min-height: 400px;">
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
                  <p v-for="(para, j) in msg.content.split('\n\n')" :key="j" :class="j > 0 ? 'mt-2' : ''">
                    {{ para }}
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

            <!-- Input area -->
            <div class="border-t border-bdr pt-3">
              <div class="flex items-center gap-2 mb-2">
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
          <div v-if="therapistNotes.length === 0" class="glass-card p-8 text-center">
            <ScrollText :size="32" class="mx-auto mb-3 text-txt-muted" />
            <p class="text-sm text-txt-muted">No session notes yet. Complete a session to see notes here.</p>
          </div>

          <div v-else class="space-y-3">
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
                  class="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-txt-muted hover:text-red-400 hover:bg-red-400/10 transition-all"
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
                <span>${{ note.cost.toFixed(4) }}</span>
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
            &larr; Back to notes
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
              <span>${{ therapistCurrentNote.cost.toFixed(4) }}</span>
            </div>
          </div>
        </template>
      </template>
    </template>

    <!-- ===== JOURNAL TAB ===== -->
    <template v-if="activeTab === 'journal'">
      <template v-if="journalView === 'list'">
        <div class="flex items-center justify-between mb-6">
          <p class="text-sm text-txt-secondary">Write, reflect, understand.</p>
          <button @click="goToCompose" class="btn-primary px-5 py-2 text-sm">New Entry</button>
        </div>
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
                <component :is="moodIcons[entry.mood_emoji]" v-if="entry.mood_emoji && moodIcons[entry.mood_emoji]" :size="24" class="text-accent flex-shrink-0" />
                <span v-else-if="entry.mood_emoji" class="text-2xl flex-shrink-0">{{ entry.mood_emoji }}</span>
                <BookOpen v-else :size="24" class="text-txt-muted flex-shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-txt-primary truncate">{{ entry.title || entry.content_preview.slice(0, 60) }}</span>
                    <span class="text-xs text-txt-muted flex-shrink-0">{{ timeAgo(entry.created_at) }}</span>
                  </div>
                  <p v-if="entry.title" class="text-sm text-txt-secondary mt-0.5 truncate">{{ entry.content_preview }}</p>
                  <div v-if="entry.reflection_count > 0" class="flex items-center gap-1 mt-1">
                    <span class="text-xs text-accent">{{ entry.reflection_count }} reflection{{ entry.reflection_count > 1 ? 's' : '' }}</span>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>
      </template>

      <template v-if="journalView === 'compose'">
        <div class="mb-6">
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr; Back</button>
          <h2 class="text-xl font-bold text-txt-primary">New Entry</h2>
        </div>
        <div class="glass-card p-6 space-y-4">
          <input v-model="composeTitle" type="text" placeholder="Title (optional)" maxlength="200" class="input-field text-lg font-medium" />
          <textarea v-model="composeContent" placeholder="What's on your mind?" maxlength="50000" rows="10" class="input-field resize-none text-sm leading-relaxed" />
          <p v-if="contentLength > 0" class="text-right text-xs" :class="contentLength > 45000 ? 'text-amber-400' : 'text-txt-muted'">{{ contentLength.toLocaleString() }}/50,000</p>
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
          <p v-if="journalError" class="text-sm text-red-400">{{ journalError }}</p>
          <button @click="saveEntry" :disabled="!composeContent.trim() || journalSubmitting" class="btn-primary w-full">
            <span v-if="journalSubmitting" class="inline-flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Saving...
            </span>
            <span v-else>Save Entry</span>
          </button>
        </div>
      </template>

      <template v-if="journalView === 'detail'">
        <div class="mb-6">
          <button @click="goToJournalList" class="text-txt-muted hover:text-txt-primary transition-colors text-sm mb-2">&larr; Back</button>
          <h2 class="text-xl font-bold text-txt-primary">Entry</h2>
        </div>
        <div v-if="loadingDetail" class="text-sm text-txt-muted">Loading...</div>
        <template v-else-if="currentEntry">
          <div class="glass-card p-6 mb-6">
            <div class="flex items-start justify-between mb-4">
              <div>
                <h2 v-if="currentEntry.title" class="text-lg font-semibold text-txt-primary mb-1">{{ currentEntry.title }}</h2>
                <div class="flex items-center gap-2 text-xs text-txt-muted">
                  <span>{{ formatDate(currentEntry.created_at) }}</span>
                  <span v-if="currentEntry.mood_emoji" class="flex items-center gap-1">
                    <component :is="moodIcons[currentEntry.mood_emoji]" :size="14" class="text-accent" v-if="moodIcons[currentEntry.mood_emoji]" />
                    <span v-else>{{ currentEntry.mood_emoji }}</span>
                    <span>{{ currentEntry.mood_label }}</span>
                  </span>
                </div>
              </div>
              <button @click="deleteEntry" class="text-xs text-txt-muted hover:text-red-400 transition-colors px-2 py-1">Delete</button>
            </div>
            <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ currentEntry.content }}</p>
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
                  <span class="text-xs text-txt-muted">{{ formatDate(reflection.created_at) }}</span>
                  <span class="text-xs text-txt-muted ml-auto">${{ reflection.cost.toFixed(4) }}</span>
                </div>
                <p class="text-sm text-txt-secondary leading-relaxed whitespace-pre-wrap">{{ reflection.content }}</p>
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
          <p v-if="journalError" class="text-sm text-red-400 mt-3">{{ journalError }}</p>
        </template>
        <div v-else class="glass-card p-6 text-center">
          <p v-if="journalError" class="text-sm text-red-400">{{ journalError }}</p>
          <p v-else class="text-sm text-txt-muted">Entry not found.</p>
        </div>
      </template>
    </template>

  </div>
</template>
