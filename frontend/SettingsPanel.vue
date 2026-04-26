<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { X, Upload, Trash2, Image, Film, Bell, BellOff, Palette } from 'lucide-vue-next'
import { useNotifications } from './composables/useNotifications'
import {
  type ThemeId,
  THEMES,
  getSavedTheme,
  saveTheme,
  saveCustomImage,
  removeCustomImage,
  getCustomImage,
  getCustomOpacity,
  saveCustomOpacity,
  saveCustomVideo,
  removeCustomVideo,
  getCustomVideo,
  getCustomVideoSpeed,
  saveCustomVideoSpeed,
  getCustomMediaType,
  setCustomVideoFlag,
} from './background-themes'
import { THEME_PRESETS, applyPreset, getActivePresetId, type PresetDefinition } from './theme-presets'
import { api } from '@core/api/client'

const emit = defineEmits<{ close: [] }>()

const selectedTheme = ref<ThemeId | string>(getSavedTheme())
const customImage = ref<string | null>(null)
const customVideoUrl = ref<string | null>(null)
const customOpacity = ref(getCustomOpacity())
const customVideoSpeed = ref(getCustomVideoSpeed())
const customMediaType = ref<'image' | 'video' | null>(getCustomMediaType())

const activePreset = ref(getActivePresetId())
const presetThemes = computed(() => THEMES.filter(t => t.id !== 'custom'))

interface UserTheme {
  id: string
  name: string
  description: string | null
  preview_color: string | null
  active_wallpaper_id: string | null
  rotation_interval_minutes: number
}
const userThemes = ref<UserTheme[]>([])

async function loadUserThemes() {
  try {
    userThemes.value = await api.get<UserTheme[]>('/api/themes/mine')
  } catch {}
}

async function selectPreset(id: string) {
  activePreset.value = id
  applyPreset(id)
  try {
    await api.put('/api/life/settings', { theme_preset: id })
  } catch { /* non-critical */ }
}
const customTheme = computed(() => THEMES.find(t => t.id === 'custom')!)
const hasCustomMedia = computed(() => !!customImage.value || !!customVideoUrl.value)

// Notifications
const notif = useNotifications()
const notifQuietStart = ref('22:00')
const notifQuietEnd = ref('08:00')
const notifReminderHour = ref(9)
const notifStreakWarnings = ref(true)
const notifDailyNudges = ref(true)
const notifMilestoneAlerts = ref(true)
const notifEnabled = ref(true)

async function initNotifPrefs() {
  await notif.loadPreferences()
  if (notif.preferences.value) {
    const p = notif.preferences.value
    notifEnabled.value = p.enabled
    notifQuietStart.value = p.quiet_start || '22:00'
    notifQuietEnd.value = p.quiet_end || '08:00'
    notifReminderHour.value = p.reminder_hour
    notifStreakWarnings.value = p.streak_warnings
    notifDailyNudges.value = p.daily_nudges
    notifMilestoneAlerts.value = p.milestone_alerts
  }
}

async function saveNotifPrefs() {
  await notif.savePreferences({
    enabled: notifEnabled.value,
    quiet_start: notifQuietStart.value,
    quiet_end: notifQuietEnd.value,
    reminder_hour: notifReminderHour.value,
    streak_warnings: notifStreakWarnings.value,
    daily_nudges: notifDailyNudges.value,
    milestone_alerts: notifMilestoneAlerts.value,
  })
}

async function handleNotifToggle() {
  if (!notif.isSubscribed.value && notifEnabled.value) {
    const ok = await notif.subscribe()
    if (!ok) {
      notifEnabled.value = false
      return
    }
  } else if (notif.isSubscribed.value && !notifEnabled.value) {
    await notif.unsubscribe()
  }
  await saveNotifPrefs()
}

onMounted(async () => {
  customImage.value = getCustomImage()
  customVideoUrl.value = await getCustomVideo()
  customMediaType.value = getCustomMediaType()
  await initNotifPrefs()
  loadUserThemes()
})

function selectTheme(id: ThemeId | string) {
  selectedTheme.value = id
  saveTheme(id)
  document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: id }))
}

function onCustomImageUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  if (file.type.startsWith('video/')) {
    handleVideoUpload(file)
    return
  }

  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result as string
    saveCustomImage(dataUrl)
    customImage.value = dataUrl
    customMediaType.value = 'image'
    setCustomVideoFlag(false)
    selectTheme('custom')
  }
  reader.readAsDataURL(file)
}

async function handleVideoUpload(file: File) {
  await saveCustomVideo(file)
  setCustomVideoFlag(true)
  customVideoUrl.value = URL.createObjectURL(file)
  customMediaType.value = 'video'
  removeCustomImage()
  customImage.value = null
  selectTheme('custom')
}

async function clearCustomMedia() {
  removeCustomImage()
  await removeCustomVideo()
  setCustomVideoFlag(false)
  customImage.value = null
  customVideoUrl.value = null
  customMediaType.value = null
  if (selectedTheme.value === 'custom') {
    selectTheme('northern-lights')
  }
}

function onOpacityChange(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  customOpacity.value = val
  saveCustomOpacity(val)
  if (selectedTheme.value === 'custom') {
    document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: 'custom' }))
  }
}

function onSpeedChange(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  customVideoSpeed.value = val
  saveCustomVideoSpeed(val)
  if (selectedTheme.value === 'custom') {
    document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: 'custom' }))
  }
}
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
        <h2 class="text-lg font-semibold text-txt-primary">Settings</h2>
        <button @click="emit('close')" class="p-1.5 rounded-lg text-txt-muted hover:text-txt-primary hover:bg-surface-3 transition-colors">
          <X :size="18" />
        </button>
      </div>

      <div class="p-5 space-y-6">
        <!-- Color Scheme Presets -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-3">Color Scheme</h3>
          <div class="grid grid-cols-3 gap-2">
            <button
              v-for="preset in THEME_PRESETS"
              :key="preset.id"
              @click="selectPreset(preset.id)"
              class="group relative rounded-xl overflow-hidden border-2 transition-all duration-200 p-3"
              :class="activePreset === preset.id ? 'border-accent shadow-lg shadow-accent/20' : 'border-bdr hover:border-txt-muted'"
            >
              <div
                class="w-full h-8 rounded-lg mb-2"
                :style="{ background: preset.preview }"
              />
              <p class="text-[11px] font-medium text-txt-primary text-center">{{ preset.name }}</p>
              <p class="text-[9px] text-txt-muted text-center leading-tight mt-0.5">{{ preset.description }}</p>
            </button>
          </div>
        </div>

        <!-- Background Theme grid -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-3">Background</h3>
          <div class="grid grid-cols-2 gap-3">
            <button
              v-for="theme in presetThemes"
              :key="theme.id"
              @click="selectTheme(theme.id)"
              class="group relative rounded-xl overflow-hidden border-2 transition-all duration-200"
              :class="selectedTheme === theme.id ? 'border-accent shadow-lg shadow-accent/20' : 'border-bdr hover:border-txt-muted'"
            >
              <div
                class="aspect-video w-full"
                :style="{ background: theme.preview }"
              />
              <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2.5 py-2">
                <p class="text-xs font-medium text-white">{{ theme.name }}</p>
                <p class="text-[10px] text-white/60 leading-tight">{{ theme.description }}</p>
              </div>
              <!-- Selected indicator -->
              <div
                v-if="selectedTheme === theme.id"
                class="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-accent flex items-center justify-center"
              >
                <svg class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </button>
            <!-- User themes (if any) -->
            <button
              v-for="userTheme in userThemes"
              :key="userTheme.id"
              @click="selectTheme(userTheme.id)"
              class="group relative rounded-xl overflow-hidden border-2 transition-all duration-200"
              :class="selectedTheme === userTheme.id ? 'border-accent shadow-lg shadow-accent/20' : 'border-bdr hover:border-txt-muted'"
            >
              <div
                class="aspect-video w-full"
                :style="{ background: userTheme.preview_color || 'linear-gradient(135deg, #2a2a3e, #1a1a2e)' }"
              />
              <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2.5 py-2">
                <p class="text-xs font-medium text-white">{{ userTheme.name }}</p>
                <p class="text-[10px] text-white/60 leading-tight">{{ userTheme.description || `${userTheme.rotation_interval_minutes}min rotation` }}</p>
              </div>
              <div
                v-if="selectedTheme === userTheme.id"
                class="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-accent flex items-center justify-center"
              >
                <svg class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </button>
          </div>
        </div>

        <!-- Custom upload -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-3">Custom</h3>

          <div v-if="hasCustomMedia" class="space-y-3">
            <!-- Preview -->
            <button
              @click="selectTheme('custom')"
              class="relative w-full rounded-xl overflow-hidden border-2 transition-all duration-200"
              :class="selectedTheme === 'custom' ? 'border-accent shadow-lg shadow-accent/20' : 'border-bdr hover:border-txt-muted'"
            >
              <img
                v-if="customMediaType === 'image' && customImage"
                :src="customImage"
                class="aspect-video w-full object-cover"
                :style="{ opacity: 1 - customOpacity }"
              />
              <div v-else-if="customMediaType === 'video'" class="aspect-video w-full bg-surface-2 flex items-center justify-center">
                <Film :size="24" class="text-txt-muted" />
                <span class="text-xs text-txt-muted ml-2">Custom Video</span>
              </div>
              <div v-if="selectedTheme === 'custom'" class="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-accent flex items-center justify-center">
                <svg class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </button>

            <!-- Opacity slider (custom) -->
            <div class="space-y-1.5">
              <label class="text-xs text-txt-muted">Overlay darkness</label>
              <input
                type="range"
                min="0" max="0.8" step="0.05"
                :value="customOpacity"
                @input="onOpacityChange"
                class="w-full accent-accent"
              />
            </div>

            <!-- Speed slider (custom video only) -->
            <div v-if="customMediaType === 'video'" class="space-y-1.5">
              <label class="text-xs text-txt-muted">Playback speed</label>
              <input
                type="range"
                min="0.2" max="1.0" step="0.1"
                :value="customVideoSpeed"
                @input="onSpeedChange"
                class="w-full accent-accent"
              />
            </div>

            <!-- Replace / Remove -->
            <div class="flex gap-2">
              <label class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-surface-2 border border-bdr text-xs text-txt-secondary hover:bg-surface-3 cursor-pointer transition-colors">
                <Upload :size="12" /> Replace
                <input type="file" accept="image/*,video/mp4,video/webm" class="hidden" @change="onCustomImageUpload" />
              </label>
              <button
                @click="clearCustomMedia"
                class="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-surface-2 border border-bdr text-xs text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 :size="12" /> Remove
              </button>
            </div>
          </div>

          <!-- Empty state — upload prompt -->
          <label
            v-else
            class="flex flex-col items-center justify-center gap-2 p-6 rounded-xl border-2 border-dashed border-bdr hover:border-txt-muted cursor-pointer transition-colors"
          >
            <div class="w-10 h-10 rounded-full bg-surface-2 flex items-center justify-center">
              <Image :size="18" class="text-txt-muted" />
            </div>
            <p class="text-xs text-txt-muted text-center">
              Drop an image or video<br />to use as your wallpaper
            </p>
            <input type="file" accept="image/*,video/mp4,video/webm" class="hidden" @change="onCustomImageUpload" />
          </label>
        </div>

        <!-- Notifications -->
        <div class="border-t border-bdr pt-6">
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-3">Notifications</h3>

          <!-- Master toggle -->
          <label class="flex items-center justify-between py-2 cursor-pointer group">
            <div class="flex items-center gap-2">
              <component :is="notifEnabled ? Bell : BellOff" :size="16" class="text-txt-muted" />
              <span class="text-sm text-txt-primary">Push notifications</span>
            </div>
            <div
              class="relative w-10 h-5 rounded-full transition-colors"
              :class="notifEnabled ? 'bg-accent' : 'bg-surface-3'"
              @click.prevent="notifEnabled = !notifEnabled; handleNotifToggle()"
            >
              <div
                class="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform"
                :class="notifEnabled ? 'translate-x-5' : 'translate-x-0.5'"
              />
            </div>
          </label>

          <p v-if="notif.permission.value === 'denied'" class="text-xs text-red-400 mt-1">
            Notifications are blocked in your browser settings. Enable them in your browser to use this feature.
          </p>

          <!-- Expanded preferences (only when enabled) -->
          <template v-if="notifEnabled && notif.isSubscribed.value">
            <!-- Notification types -->
            <div class="mt-4 space-y-2">
              <label class="flex items-center justify-between py-1.5">
                <span class="text-xs text-txt-secondary">Streak reminders</span>
                <input type="checkbox" v-model="notifStreakWarnings" @change="saveNotifPrefs" class="accent-accent" />
              </label>
              <label class="flex items-center justify-between py-1.5">
                <span class="text-xs text-txt-secondary">Daily nudges</span>
                <input type="checkbox" v-model="notifDailyNudges" @change="saveNotifPrefs" class="accent-accent" />
              </label>
              <label class="flex items-center justify-between py-1.5">
                <span class="text-xs text-txt-secondary">Milestone alerts</span>
                <input type="checkbox" v-model="notifMilestoneAlerts" @change="saveNotifPrefs" class="accent-accent" />
              </label>
            </div>

            <!-- Quiet hours -->
            <div class="mt-4 space-y-2">
              <p class="text-xs font-medium text-txt-secondary">Quiet hours</p>
              <div class="flex items-center gap-2">
                <input
                  type="time"
                  v-model="notifQuietStart"
                  @change="saveNotifPrefs"
                  class="bg-surface-2 border border-bdr rounded px-2 py-1 text-xs text-txt-primary w-24"
                />
                <span class="text-xs text-txt-muted">to</span>
                <input
                  type="time"
                  v-model="notifQuietEnd"
                  @change="saveNotifPrefs"
                  class="bg-surface-2 border border-bdr rounded px-2 py-1 text-xs text-txt-primary w-24"
                />
              </div>
            </div>

            <!-- Reminder hour -->
            <div class="mt-4 space-y-1.5">
              <p class="text-xs font-medium text-txt-secondary">Daily reminder time</p>
              <select
                v-model.number="notifReminderHour"
                @change="saveNotifPrefs"
                class="bg-surface-2 border border-bdr rounded px-2 py-1.5 text-xs text-txt-primary w-full"
              >
                <option v-for="h in 24" :key="h - 1" :value="h - 1">
                  {{ (h - 1).toString().padStart(2, '0') }}:00
                </option>
              </select>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
