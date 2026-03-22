<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, getToken } from '@core/api/client'
import {
  Smile, Target, Trophy, BookOpen, Headphones,
  Brain, Trash2, Download, AlertTriangle, Loader2,
} from 'lucide-vue-next'

// ─── Meditation defaults ────────────────────────────────────────────────────

const medLength = ref<string>('medium')
const medVoice = ref<string>('nova')
const medAmbience = ref<string>('rain')
const savedIndicator = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | null = null

async function fetchSettings() {
  try {
    const data = await api.get<{ med_length: string; med_voice: string; med_ambience: string }>(
      '/api/life/settings',
    )
    medLength.value = data.med_length ?? 'medium'
    medVoice.value = data.med_voice ?? 'nova'
    medAmbience.value = data.med_ambience ?? 'rain'
  } catch {
    // silently keep defaults — server may not have a record yet
  }
}

async function saveMedSettings() {
  try {
    await api.put('/api/life/settings', {
      med_length: medLength.value,
      med_voice: medVoice.value,
      med_ambience: medAmbience.value,
    })
    if (savedTimer) clearTimeout(savedTimer)
    savedIndicator.value = true
    savedTimer = setTimeout(() => {
      savedIndicator.value = false
    }, 2000)
  } catch {
    // non-fatal — no toast needed here; the field just won't show "Saved"
  }
}

onMounted(fetchSettings)

// ─── Confirmation modal ──────────────────────────────────────────────────────

interface ResetItem {
  key: string
  label: string
  description: string
  endpoint: string
  isAll?: boolean
}

const resetItems: ResetItem[] = [
  {
    key: 'mood',
    label: 'Mood History',
    description: 'Clear all mood entries and streaks',
    endpoint: '/api/life/data/reset/mood',
  },
  {
    key: 'habits',
    label: 'Habit Data',
    description: 'Clear all habits, logs, and insights',
    endpoint: '/api/life/data/reset/habits',
  },
  {
    key: 'goals',
    label: 'Goals',
    description: 'Clear all goals, milestones, and habit links',
    endpoint: '/api/life/data/reset/goals',
  },
  {
    key: 'journal',
    label: 'Journal',
    description: 'Clear all journal entries and reflections',
    endpoint: '/api/life/data/reset/journal',
  },
  {
    key: 'meditation',
    label: 'Meditation Sessions',
    description: 'Clear all sessions and audio files',
    endpoint: '/api/life/data/reset/meditation',
  },
  {
    key: 'therapist',
    label: 'Therapist Notes',
    description: 'Clear all therapy session notes',
    endpoint: '/api/life/data/reset/therapist',
  },
]

const allResetItem: ResetItem = {
  key: 'all',
  label: 'Reset All ZugaLife Data',
  description: 'Clear everything above. Settings are preserved.',
  endpoint: '/api/life/data/reset/all',
  isAll: true,
}

// Icon map keyed by reset item key
const resetIcons: Record<string, unknown> = {
  mood: Smile,
  habits: Target,
  goals: Trophy,
  journal: BookOpen,
  meditation: Headphones,
  therapist: Brain,
  all: AlertTriangle,
}

const modalVisible = ref(false)
const modalItem = ref<ResetItem | null>(null)
const modalResetInput = ref('')
const modalLoading = ref(false)
const modalSuccess = ref(false)

function openModal(item: ResetItem) {
  modalItem.value = item
  modalResetInput.value = ''
  modalLoading.value = false
  modalSuccess.value = false
  modalVisible.value = true
}

function closeModal() {
  if (modalLoading.value) return
  modalVisible.value = false
  modalItem.value = null
}

const confirmEnabled = computed(() => {
  if (!modalItem.value) return false
  if (modalItem.value.isAll) return modalResetInput.value === 'RESET'
  return true
})

async function confirmReset() {
  if (!modalItem.value || !confirmEnabled.value || modalLoading.value) return
  modalLoading.value = true
  try {
    await api.delete(modalItem.value.endpoint)
    modalSuccess.value = true
    setTimeout(() => {
      modalVisible.value = false
      modalItem.value = null
      modalSuccess.value = false
    }, 1200)
  } catch {
    // keep modal open — user can retry or cancel
  } finally {
    modalLoading.value = false
  }
}

// ─── Export ──────────────────────────────────────────────────────────────────

function exportJournal() {
  const token = getToken()
  const url = token
    ? `/api/life/journal/export?format=zip&token=${encodeURIComponent(token)}`
    : '/api/life/journal/export?format=zip'
  window.open(url, '_blank')
}
</script>

<template>
  <div class="space-y-8">

    <!-- ── Section 1: Meditation Defaults ──────────────────────────────────── -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="flex items-start justify-between mb-5">
        <div>
          <h2 class="text-base font-semibold text-txt-primary">Meditation Defaults</h2>
          <p class="text-sm text-txt-muted mt-0.5">Configure your default meditation preferences</p>
        </div>
        <!-- "Saved" indicator -->
        <Transition
          enter-active-class="transition-opacity duration-150"
          leave-active-class="transition-opacity duration-500"
          enter-from-class="opacity-0"
          leave-to-class="opacity-0"
        >
          <span
            v-if="savedIndicator"
            class="text-xs font-medium text-green-400 bg-green-400/10 px-2.5 py-1 rounded-full"
          >
            Saved
          </span>
        </Transition>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <!-- Length -->
        <div>
          <label class="block text-sm font-medium text-txt-secondary mb-1.5">Length</label>
          <select
            v-model="medLength"
            @change="saveMedSettings"
            class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 transition-colors"
          >
            <option value="short">Short</option>
            <option value="medium">Medium</option>
            <option value="long">Long</option>
          </select>
        </div>

        <!-- Voice -->
        <div>
          <label class="block text-sm font-medium text-txt-secondary mb-1.5">Voice</label>
          <select
            v-model="medVoice"
            @change="saveMedSettings"
            class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 transition-colors"
          >
            <option value="alloy">Alloy</option>
            <option value="echo">Echo</option>
            <option value="fable">Fable</option>
            <option value="onyx">Onyx</option>
            <option value="nova">Nova</option>
            <option value="shimmer">Shimmer</option>
          </select>
        </div>

        <!-- Ambience -->
        <div>
          <label class="block text-sm font-medium text-txt-secondary mb-1.5">Ambience</label>
          <select
            v-model="medAmbience"
            @change="saveMedSettings"
            class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 transition-colors"
          >
            <option value="rain">Rain</option>
            <option value="ocean">Ocean</option>
            <option value="forest">Forest</option>
            <option value="bowls">Bowls</option>
            <option value="silence">Silence</option>
          </select>
        </div>
      </div>
    </div>

    <!-- ── Section 2: Data Management ──────────────────────────────────────── -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="mb-5">
        <h2 class="text-base font-semibold text-txt-primary">Data Management</h2>
        <p class="text-sm text-txt-muted mt-0.5">Reset or clear your ZugaLife data</p>
      </div>

      <p class="flex items-center gap-1.5 text-sm text-red-400/80 mb-5">
        <AlertTriangle :size="14" class="shrink-0" />
        These actions are permanent and cannot be undone.
      </p>

      <div class="space-y-2">
        <!-- Individual reset items -->
        <div
          v-for="item in resetItems"
          :key="item.key"
          class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg bg-surface-2/50 hover:bg-surface-2 transition-colors"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-surface-3 flex items-center justify-center shrink-0">
              <component :is="resetIcons[item.key]" :size="15" class="text-txt-muted" />
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium text-txt-primary truncate">{{ item.label }}</p>
              <p class="text-xs text-txt-muted truncate">{{ item.description }}</p>
            </div>
          </div>
          <button
            @click="openModal(item)"
            class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/20 bg-red-500/5 text-xs font-medium text-red-400 hover:bg-red-500/15 hover:border-red-500/40 transition-colors"
          >
            <Trash2 :size="12" />
            Reset
          </button>
        </div>

        <!-- Divider -->
        <div class="border-t border-bdr my-4" />

        <!-- Reset All -->
        <div class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg border border-red-500/30 bg-red-500/5">
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center shrink-0">
              <AlertTriangle :size="15" class="text-red-400" />
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium text-txt-primary truncate">{{ allResetItem.label }}</p>
              <p class="text-xs text-txt-muted truncate">{{ allResetItem.description }}</p>
            </div>
          </div>
          <button
            @click="openModal(allResetItem)"
            class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/40 bg-red-500/15 text-xs font-medium text-red-400 hover:bg-red-500/25 hover:border-red-500/60 transition-colors"
          >
            <Trash2 :size="12" />
            Reset All
          </button>
        </div>
      </div>
    </div>

    <!-- ── Section 3: Export ────────────────────────────────────────────────── -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="mb-5">
        <h2 class="text-base font-semibold text-txt-primary">Export</h2>
        <p class="text-sm text-txt-muted mt-0.5">Download your data</p>
      </div>

      <div class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg bg-surface-2/50">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-surface-3 flex items-center justify-center shrink-0">
            <BookOpen :size="15" class="text-txt-muted" />
          </div>
          <div>
            <p class="text-sm font-medium text-txt-primary">Journal Export</p>
            <p class="text-xs text-txt-muted">Download all journal entries as a ZIP file</p>
          </div>
        </div>
        <button
          @click="exportJournal"
          class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-bdr bg-surface-2 text-xs font-medium text-txt-secondary hover:bg-surface-3 hover:text-txt-primary transition-colors"
        >
          <Download :size="12" />
          Export Journal
        </button>
      </div>
    </div>

  </div>

  <!-- ── Confirmation Modal ───────────────────────────────────────────────── -->
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <div
        v-if="modalVisible && modalItem"
        class="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
        @click.self="closeModal"
      >
        <Transition
          enter-active-class="transition-all duration-200"
          leave-active-class="transition-all duration-150"
          enter-from-class="opacity-0 scale-95"
          leave-to-class="opacity-0 scale-95"
        >
          <div
            v-if="modalVisible"
            class="bg-surface-1 rounded-xl border border-bdr p-6 w-full max-w-md shadow-2xl"
            @click.stop
          >
            <!-- Success state -->
            <template v-if="modalSuccess">
              <div class="flex flex-col items-center gap-3 py-4">
                <div class="w-12 h-12 rounded-full bg-green-500/10 flex items-center justify-center">
                  <svg class="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <p class="text-sm font-medium text-txt-primary">Reset complete</p>
              </div>
            </template>

            <!-- Normal state -->
            <template v-else>
              <div class="flex items-start gap-3 mb-4">
                <div class="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <AlertTriangle :size="18" class="text-red-400" />
                </div>
                <div>
                  <h3 class="text-base font-semibold text-txt-primary">
                    Reset {{ modalItem.label }}?
                  </h3>
                  <p class="text-sm text-txt-muted mt-1">
                    This will permanently delete all your {{ modalItem.description.toLowerCase() }}. This cannot be undone.
                  </p>
                </div>
              </div>

              <!-- "Type RESET" requirement for reset-all -->
              <div v-if="modalItem.isAll" class="mb-5">
                <label class="block text-sm font-medium text-txt-secondary mb-1.5">
                  Type <span class="font-mono text-red-400">RESET</span> to confirm
                </label>
                <input
                  v-model="modalResetInput"
                  type="text"
                  placeholder="RESET"
                  autocomplete="off"
                  class="w-full bg-surface-2 border border-bdr rounded-lg px-3 py-2 text-sm text-txt-primary placeholder:text-txt-muted focus:outline-none focus:ring-1 focus:ring-red-500/50 focus:border-red-500/50 transition-colors font-mono"
                />
              </div>

              <div class="flex items-center justify-end gap-3">
                <button
                  @click="closeModal"
                  :disabled="modalLoading"
                  class="px-4 py-2 rounded-lg text-sm font-medium text-txt-secondary hover:text-txt-primary hover:bg-surface-2 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  @click="confirmReset"
                  :disabled="!confirmEnabled || modalLoading"
                  class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-500 hover:bg-red-600 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Loader2 v-if="modalLoading" :size="14" class="animate-spin" />
                  <Trash2 v-else :size="14" />
                  Confirm Reset
                </button>
              </div>
            </template>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
