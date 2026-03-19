<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { X, User, Globe } from 'lucide-vue-next'
import { api } from '@core/api/client'

const emit = defineEmits<{ close: []; settingsLoaded: [settings: UserSettings] }>()

// --- Server-synced settings ---

interface UserSettings {
  display_name: string | null
  timezone: string
  theme: string
  theme_opacity: number
  med_duration: number
  med_voice: string
  med_ambience: string
}

const serverSettings = ref<UserSettings | null>(null)
const displayName = ref('')
const timezone = ref('America/New_York')
const saving = ref(false)
const saveStatus = ref<'idle' | 'saved' | 'error'>('idle')

let saveTimer: ReturnType<typeof setTimeout> | null = null

async function fetchSettings() {
  try {
    const res = await api.get<UserSettings>('/api/life/settings')
    serverSettings.value = res
    displayName.value = res.display_name || ''
    timezone.value = res.timezone
    emit('settingsLoaded', res)
  } catch (e) {
    console.error('Failed to load settings:', e)
  }
}

async function saveToServer(updates: Partial<UserSettings>) {
  saving.value = true
  saveStatus.value = 'idle'
  try {
    const res = await api.put<UserSettings>('/api/life/settings', updates)
    serverSettings.value = res
    saveStatus.value = 'saved'
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch (e) {
    console.error('Failed to save settings:', e)
    saveStatus.value = 'error'
  } finally {
    saving.value = false
  }
}

function debouncedSave(updates: Partial<UserSettings>) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveToServer(updates), 600)
}

function onDisplayNameInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  displayName.value = val
  debouncedSave({ display_name: val || null })
}

function onTimezoneChange(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  timezone.value = val
  saveToServer({ timezone: val })
}

// --- Common timezones ---
const TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern (ET)' },
  { value: 'America/Chicago', label: 'Central (CT)' },
  { value: 'America/Denver', label: 'Mountain (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific (PT)' },
  { value: 'America/Anchorage', label: 'Alaska (AKT)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii (HT)' },
  { value: 'UTC', label: 'UTC' },
  { value: 'Europe/London', label: 'London (GMT/BST)' },
  { value: 'Europe/Paris', label: 'Central Europe (CET)' },
  { value: 'Europe/Berlin', label: 'Berlin (CET)' },
  { value: 'Asia/Tokyo', label: 'Tokyo (JST)' },
  { value: 'Asia/Shanghai', label: 'China (CST)' },
  { value: 'Asia/Kolkata', label: 'India (IST)' },
  { value: 'Australia/Sydney', label: 'Sydney (AEST)' },
]

onMounted(fetchSettings)
</script>

<template>
  <!-- Backdrop -->
  <div class="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm" @click="emit('close')">
    <!-- Panel -->
    <div
      class="absolute right-0 top-0 h-full w-full max-w-sm bg-surface-1 border-l border-bdr shadow-2xl overflow-y-auto"
      @click.stop
    >
      <!-- Header -->
      <div class="flex items-center justify-between p-5 border-b border-bdr sticky top-0 bg-surface-1 z-10">
        <div class="flex items-center gap-2">
          <h2 class="text-lg font-semibold text-txt-primary">Settings</h2>
          <transition name="fade">
            <span v-if="saveStatus === 'saved'" class="text-[10px] text-green-400 font-medium">Saved</span>
            <span v-else-if="saveStatus === 'error'" class="text-[10px] text-red-400 font-medium">Error</span>
            <span v-else-if="saving" class="text-[10px] text-txt-muted font-medium">Saving...</span>
          </transition>
        </div>
        <button @click="emit('close')" class="p-1.5 rounded-lg text-txt-muted hover:text-txt-primary hover:bg-surface-3 transition-colors">
          <X :size="18" />
        </button>
      </div>

      <div class="p-5 space-y-6">
        <!-- Profile section -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-4">Profile</h3>

          <div class="space-y-4">
            <!-- Display name -->
            <div class="space-y-1.5">
              <label class="text-xs text-txt-muted flex items-center gap-1.5">
                <User :size="12" /> Display Name
              </label>
              <input
                type="text"
                :value="displayName"
                @input="onDisplayNameInput"
                placeholder="How should we greet you?"
                maxlength="100"
                class="w-full px-3 py-2 rounded-lg bg-surface-2 border border-bdr text-sm text-txt-primary
                       placeholder:text-txt-muted/50 focus:outline-none focus:border-accent transition-colors"
              />
            </div>

            <!-- Timezone -->
            <div class="space-y-1.5">
              <label class="text-xs text-txt-muted flex items-center gap-1.5">
                <Globe :size="12" /> Timezone
              </label>
              <select
                :value="timezone"
                @change="onTimezoneChange"
                class="w-full px-3 py-2 rounded-lg bg-surface-2 border border-bdr text-sm text-txt-primary
                       focus:outline-none focus:border-accent transition-colors appearance-none cursor-pointer"
              >
                <option v-for="tz in TIMEZONES" :key="tz.value" :value="tz.value">
                  {{ tz.label }}
                </option>
              </select>
              <p class="text-[10px] text-txt-muted leading-relaxed">
                Affects streaks, greetings, and daily resets.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
