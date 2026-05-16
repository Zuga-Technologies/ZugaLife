<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
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

// ─── Wellness avatar ────────────────────────────────────────────────────────

const avatarEnabled = ref(localStorage.getItem('zugalife_avatar_enabled') !== '0')

watch(avatarEnabled, (v) => {
  localStorage.setItem('zugalife_avatar_enabled', v ? '1' : '0')
})

// ─── Voice input (Whisper STT) ──────────────────────────────────────────────
// Independent of avatar / TTS — works in text-mode and avatar-mode alike.
// Cost is metered through the BE's record_spend so it shows in the same
// ZugaTokens transaction log as chat and TTS.
const voiceInputEnabled = ref(localStorage.getItem('zugalife_voice_input_enabled') !== '0')

watch(voiceInputEnabled, (v) => {
  localStorage.setItem('zugalife_voice_input_enabled', v ? '1' : '0')
})

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

onMounted(() => {
  fetchSettings()
  loadConsent()
})

// ─── Confirmation modal ──────────────────────────────────────────────────────

interface ResetItem {
  key: string
  label: string
  description: string
  endpoint: string
  isAll?: boolean
  // When true, the endpoint is DELETE /api/life/users/me — full account
  // deletion + 30d SLA stamp. Requires typing DELETE to confirm.
  isDeleteAccount?: boolean
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

const deleteAccountItem: ResetItem = {
  key: 'delete_account',
  label: 'Delete ZugaLife Account',
  description: 'Revoke all consents and purge every record (mood, journal, habits, goals, meditation, therapist notes, gamification, settings). Stamps the 30-day SLA window we promise for cache/log purge.',
  endpoint: '/api/life/users/me',
  isDeleteAccount: true,
}

// ─── Consent state (loaded for display in Privacy section) ────────────────────

interface ConsentState {
  health_collected_at: string | null
  ai_sharing_at: string | null
  age_confirmed_at: string | null
  deletion_requested_at: string | null
}

const consentState = ref<ConsentState | null>(null)
const consentLoading = ref(false)

async function loadConsent() {
  consentLoading.value = true
  try {
    consentState.value = await api.get<ConsentState>('/api/life/consent')
  } catch {
    consentState.value = null
  } finally {
    consentLoading.value = false
  }
}

function fmtTs(ts: string | null): string {
  if (!ts) return 'Not given'
  try {
    return new Date(ts).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  } catch {
    return ts
  }
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

const modalDialogRef = ref<HTMLElement | null>(null)
const modalInputRef = ref<HTMLInputElement | null>(null)

function openModal(item: ResetItem) {
  modalItem.value = item
  modalResetInput.value = ''
  modalLoading.value = false
  modalSuccess.value = false
  modalVisible.value = true
  // Focus the type-to-confirm input if present, else the dialog itself so
  // NVDA announces the dialog title + description.
  nextTick(() => {
    if (modalInputRef.value) modalInputRef.value.focus()
    else if (modalDialogRef.value) modalDialogRef.value.focus()
  })
}

function closeModal() {
  if (modalLoading.value) return
  modalVisible.value = false
  modalItem.value = null
}

function onModalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && modalVisible.value && !modalLoading.value) {
    e.preventDefault()
    closeModal()
  }
}

watch(modalVisible, (open) => {
  if (open) window.addEventListener('keydown', onModalKeydown)
  else window.removeEventListener('keydown', onModalKeydown)
})

const confirmEnabled = computed(() => {
  if (!modalItem.value) return false
  if (modalItem.value.isDeleteAccount) return modalResetInput.value === 'DELETE'
  if (modalItem.value.isAll) return modalResetInput.value === 'RESET'
  return true
})

async function confirmReset() {
  if (!modalItem.value || !confirmEnabled.value || modalLoading.value) return
  modalLoading.value = true
  try {
    await api.delete(modalItem.value.endpoint)
    modalSuccess.value = true
    if (modalItem.value.isDeleteAccount) {
      await loadConsent()
    }
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

    <!-- ── Section 2: Wellness Avatar ──────────────────────────────────────── -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="flex items-start justify-between mb-5">
        <div>
          <h2 class="text-base font-semibold text-txt-primary">Wellness Avatar</h2>
          <p class="text-sm text-txt-muted mt-0.5">
            Turn the wellness bot into a 3D character that speaks her replies aloud.
            The text chat stays the same — the avatar is presence on top, for the
            psychological weight of being seen and heard.
          </p>
        </div>
      </div>

      <label class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg bg-surface-2/50 cursor-pointer">
        <span class="text-sm text-txt-secondary">Show avatar &amp; speak replies</span>
        <input type="checkbox" v-model="avatarEnabled" class="accent-accent" />
      </label>
    </div>

    <!-- ── Section 2b: Voice Input ─────────────────────────────────────────── -->
    <!-- Separate from avatar/TTS. Works in text-mode and avatar-mode alike.
         Costs ZugaTokens per recording (Whisper-1: ~$0.006/min, billed
         through the same ledger as chat). -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="flex items-start justify-between mb-5">
        <div>
          <h2 class="text-base font-semibold text-txt-primary">Voice Input</h2>
          <p class="text-sm text-txt-muted mt-0.5">
            Speak instead of typing — transcribed via Whisper. Each recording uses ZugaTokens.
          </p>
        </div>
      </div>

      <label class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg bg-surface-2/50 cursor-pointer">
        <span class="text-sm text-txt-secondary">Enable voice input (mic button in chat)</span>
        <input type="checkbox" v-model="voiceInputEnabled" class="accent-accent" />
      </label>
    </div>

    <!-- ── Section 3: Data Management ──────────────────────────────────────── -->
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

    <!-- ── Section 4: Export ────────────────────────────────────────────────── -->
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

    <!-- ── Section 5: Privacy & Consent ─────────────────────────────────── -->
    <!-- WA MHMDA + CA CMIA + COPPA revocation surface. Issue #3 follow-up. -->
    <div class="bg-surface-1 rounded-xl border border-bdr p-6">
      <div class="mb-5">
        <h2 class="text-base font-semibold text-txt-primary">Privacy &amp; Consent</h2>
        <p class="text-sm text-txt-muted mt-0.5">
          Review what you've agreed to and revoke at any time
        </p>
      </div>

      <!-- Consent state grid -->
      <div class="space-y-2 mb-4">
        <div class="flex items-center justify-between gap-4 py-2.5 px-4 rounded-lg bg-surface-2/50">
          <p class="text-sm text-txt-secondary">Wellness data collection</p>
          <p class="text-xs font-mono"
            :class="consentState?.health_collected_at ? 'text-accent' : 'text-txt-muted'">
            {{ fmtTs(consentState?.health_collected_at ?? null) }}
          </p>
        </div>
        <div class="flex items-center justify-between gap-4 py-2.5 px-4 rounded-lg bg-surface-2/50">
          <p class="text-sm text-txt-secondary">AI sharing (Venice — therapist)</p>
          <p class="text-xs font-mono"
            :class="consentState?.ai_sharing_at ? 'text-accent' : 'text-txt-muted'">
            {{ fmtTs(consentState?.ai_sharing_at ?? null) }}
          </p>
        </div>
        <div class="flex items-center justify-between gap-4 py-2.5 px-4 rounded-lg bg-surface-2/50">
          <p class="text-sm text-txt-secondary">Age confirmed (13+)</p>
          <p class="text-xs font-mono"
            :class="consentState?.age_confirmed_at ? 'text-accent' : 'text-txt-muted'">
            {{ fmtTs(consentState?.age_confirmed_at ?? null) }}
          </p>
        </div>
        <div
          v-if="consentState?.deletion_requested_at"
          class="flex items-center justify-between gap-4 py-2.5 px-4 rounded-lg border border-amber-500/30 bg-amber-500/5"
        >
          <p class="text-sm text-amber-300">Deletion requested</p>
          <p class="text-xs font-mono text-amber-300">
            {{ fmtTs(consentState.deletion_requested_at) }}
          </p>
        </div>
      </div>

      <!-- Divider -->
      <div class="border-t border-bdr my-4" />

      <!-- Delete account = revocation. Always available, even without consent. -->
      <div class="flex items-center justify-between gap-4 py-3 px-4 rounded-lg border border-red-500/30 bg-red-500/5">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center shrink-0">
            <AlertTriangle :size="15" class="text-red-400" />
          </div>
          <div class="min-w-0">
            <p class="text-sm font-medium text-txt-primary truncate">{{ deleteAccountItem.label }}</p>
            <p class="text-xs text-txt-muted">{{ deleteAccountItem.description }}</p>
          </div>
        </div>
        <button
          @click="openModal(deleteAccountItem)"
          class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/40 bg-red-500/15 text-xs font-medium text-red-400 hover:bg-red-500/25 hover:border-red-500/60 transition-colors"
        >
          <Trash2 :size="12" />
          Delete account
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
            ref="modalDialogRef"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lifeModalTitle"
            aria-describedby="lifeModalDesc"
            tabindex="-1"
            class="bg-surface-1 rounded-xl border border-bdr p-6 w-full max-w-md shadow-2xl focus:outline-none"
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
                <p class="text-sm font-medium text-txt-primary">
                  {{ modalItem?.isDeleteAccount ? 'Account purged' : 'Reset complete' }}
                </p>
              </div>
            </template>

            <!-- Normal state -->
            <template v-else>
              <div class="flex items-start gap-3 mb-4">
                <div class="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center shrink-0 mt-0.5">
                  <AlertTriangle :size="18" class="text-red-400" />
                </div>
                <div>
                  <h3 id="lifeModalTitle" class="text-base font-semibold text-txt-primary">
                    <template v-if="modalItem.isDeleteAccount">
                      Delete your ZugaLife account?
                    </template>
                    <template v-else>
                      Reset {{ modalItem.label }}?
                    </template>
                  </h3>
                  <p id="lifeModalDesc" class="text-sm text-txt-muted mt-1">
                    <template v-if="modalItem.isDeleteAccount">
                      This revokes all consents and purges every ZugaLife record
                      tied to your account. We then have 30 days to scrub backups,
                      caches, and any third-party copies. This cannot be undone.
                    </template>
                    <template v-else>
                      This will permanently delete all your {{ modalItem.description.toLowerCase() }}. This cannot be undone.
                    </template>
                  </p>
                </div>
              </div>

              <!-- Type-to-confirm gate (RESET or DELETE) -->
              <div v-if="modalItem.isAll || modalItem.isDeleteAccount" class="mb-5">
                <label for="lifeModalConfirmInput" class="block text-sm font-medium text-txt-secondary mb-1.5">
                  Type
                  <span class="font-mono text-red-400">
                    {{ modalItem.isDeleteAccount ? 'DELETE' : 'RESET' }}
                  </span>
                  to confirm
                </label>
                <input
                  id="lifeModalConfirmInput"
                  ref="modalInputRef"
                  v-model="modalResetInput"
                  type="text"
                  :placeholder="modalItem.isDeleteAccount ? 'DELETE' : 'RESET'"
                  :aria-label="modalItem.isDeleteAccount ? 'Type DELETE to confirm account deletion' : 'Type RESET to confirm'"
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
                  {{ modalItem.isDeleteAccount ? 'Delete account' : 'Confirm Reset' }}
                </button>
              </div>
            </template>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>
