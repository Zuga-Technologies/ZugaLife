<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { X, Upload, Trash2, Film, ImageIcon, Download, FileText, FileJson } from 'lucide-vue-next'
import { getToken } from '@core/api/client'
import {
  type ThemeId,
  THEMES,
  getSavedTheme,
  saveTheme,
  getCustomImage,
  saveCustomImage,
  removeCustomImage,
  getCustomOpacity,
  saveCustomOpacity,
  getCustomVideo,
  saveCustomVideo,
  removeCustomVideo,
  getCustomVideoSpeed,
  saveCustomVideoSpeed,
  getCustomMediaType,
  setCustomVideoFlag,
} from './background-themes'

const emit = defineEmits<{ close: [] }>()

const selectedTheme = ref<ThemeId>(getSavedTheme())
const customOpacity = ref(getCustomOpacity())
const customVideoSpeed = ref(getCustomVideoSpeed())
const customImagePreview = ref<string | null>(getCustomImage())
const customVideoPreview = ref<string | null>(null)
const customMediaType = ref<'image' | 'video' | null>(getCustomMediaType())
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

const showCustomControls = computed(() => selectedTheme.value === 'custom')
const hasCustomMedia = computed(() => customMediaType.value !== null)

// Load video preview from IndexedDB on mount
onMounted(async () => {
  if (customMediaType.value === 'video') {
    customVideoPreview.value = await getCustomVideo()
  }
})

function selectTheme(id: ThemeId) {
  selectedTheme.value = id
  saveTheme(id)
  document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: id }))
}

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const VIDEO_TYPES = ['video/mp4', 'video/webm']
const ALL_ACCEPT = [...IMAGE_TYPES, ...VIDEO_TYPES].join(',')

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const isImage = IMAGE_TYPES.includes(file.type)
  const isVideo = VIDEO_TYPES.includes(file.type)

  if (!isImage && !isVideo) {
    alert('Please use JPG, PNG, WebP, MP4, or WebM.')
    return
  }

  if (isImage && file.size > 5 * 1024 * 1024) {
    alert('Image must be under 5 MB.')
    return
  }
  if (isVideo && file.size > 20 * 1024 * 1024) {
    alert('Video must be under 20 MB.')
    return
  }

  uploading.value = true

  if (isImage) {
    // Clear any existing video
    await removeCustomVideo()
    setCustomVideoFlag(false)
    customVideoPreview.value = null

    const reader = new FileReader()
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string
      saveCustomImage(dataUrl)
      customImagePreview.value = dataUrl
      customMediaType.value = 'image'
      uploading.value = false
      selectTheme('custom')
    }
    reader.readAsDataURL(file)
  } else {
    // Clear any existing image
    removeCustomImage()
    customImagePreview.value = null

    await saveCustomVideo(file)
    setCustomVideoFlag(true)
    customVideoPreview.value = URL.createObjectURL(file)
    customMediaType.value = 'video'
    uploading.value = false
    selectTheme('custom')
  }

  // Reset file input so same file can be re-selected
  target.value = ''
}

async function clearCustomMedia() {
  removeCustomImage()
  await removeCustomVideo()
  setCustomVideoFlag(false)
  customImagePreview.value = null
  customVideoPreview.value = null
  customMediaType.value = null
  if (selectedTheme.value === 'custom') selectTheme('none')
}

function updateOpacity(event: Event) {
  const val = parseFloat((event.target as HTMLInputElement).value)
  customOpacity.value = val
  saveCustomOpacity(val)
  document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: 'custom' }))
}

function updateVideoSpeed(event: Event) {
  const val = parseFloat((event.target as HTMLInputElement).value)
  customVideoSpeed.value = val
  saveCustomVideoSpeed(val)
  document.dispatchEvent(new CustomEvent('zugalife-theme-change', { detail: 'custom' }))
}

// --- Data Export ---

const exporting = ref(false)
const exportError = ref('')

async function exportJournal(format: 'markdown' | 'json') {
  exporting.value = true
  exportError.value = ''

  try {
    const res = await fetch(`/api/life/journal/export?format=${format}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })

    if (!res.ok) {
      if (res.status === 404) {
        exportError.value = 'No journal entries to export yet.'
      } else {
        exportError.value = 'Export failed — try again.'
      }
      return
    }

    // Trigger browser download
    const blob = await res.blob()
    const ext = format === 'json' ? 'json' : 'zip'
    const filename = `zugalife-journal.${ext}`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    exportError.value = 'Network error — check your connection.'
  } finally {
    exporting.value = false
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
        <!-- Appearance section -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-4">Background</h3>

          <!-- Theme grid -->
          <div class="grid grid-cols-2 gap-3">
            <button
              v-for="theme in THEMES"
              :key="theme.id"
              @click="selectTheme(theme.id)"
              class="group relative rounded-xl overflow-hidden border-2 transition-all duration-200"
              :class="selectedTheme === theme.id
                ? 'border-accent shadow-lg shadow-accent/20'
                : 'border-bdr hover:border-bdr-hover'"
            >
              <!-- Preview swatch -->
              <div
                class="h-16 w-full"
                :style="{ background: theme.preview }"
              />
              <!-- Label -->
              <div class="p-2 bg-surface-2">
                <p class="text-xs font-medium text-txt-primary truncate">{{ theme.name }}</p>
                <p class="text-[10px] text-txt-muted mt-0.5 leading-tight line-clamp-2">{{ theme.description }}</p>
              </div>
              <!-- Selected check -->
              <div
                v-if="selectedTheme === theme.id"
                class="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-accent flex items-center justify-center"
              >
                <svg class="w-3 h-3 text-surface-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
            </button>
          </div>
        </div>

        <!-- Custom media controls -->
        <div v-if="showCustomControls" class="space-y-4">
          <div class="glass-card p-4 space-y-3">
            <p class="text-xs text-txt-secondary font-medium">Custom Background</p>

            <!-- Upload area -->
            <div
              v-if="!hasCustomMedia"
              @click="fileInput?.click()"
              class="flex flex-col items-center gap-2 py-6 border-2 border-dashed border-bdr rounded-lg cursor-pointer hover:border-bdr-hover transition-colors"
            >
              <Upload :size="24" class="text-txt-muted" />
              <p class="text-xs text-txt-muted">Click to upload</p>
              <p class="text-[10px] text-txt-muted">Image (JPG, PNG, WebP) — max 5 MB</p>
              <p class="text-[10px] text-txt-muted">Video (MP4, WebM) — max 20 MB</p>
            </div>

            <!-- Uploading spinner -->
            <div v-if="uploading" class="flex items-center justify-center py-6">
              <div class="w-6 h-6 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
              <span class="text-xs text-txt-muted ml-2">Saving...</span>
            </div>

            <!-- Image preview -->
            <div v-if="customMediaType === 'image' && customImagePreview && !uploading" class="relative rounded-lg overflow-hidden">
              <div class="absolute top-2 left-2 flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/50 text-[10px] text-white/70">
                <ImageIcon :size="10" /> Image
              </div>
              <img :src="customImagePreview" class="w-full h-24 object-cover" alt="Custom background" />
              <button
                @click="clearCustomMedia"
                class="absolute top-2 right-2 p-1 rounded-md bg-black/60 text-white hover:bg-red-600 transition-colors"
              >
                <Trash2 :size="14" />
              </button>
            </div>

            <!-- Video preview -->
            <div v-if="customMediaType === 'video' && customVideoPreview && !uploading" class="relative rounded-lg overflow-hidden">
              <div class="absolute top-2 left-2 z-10 flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/50 text-[10px] text-white/70">
                <Film :size="10" /> Video
              </div>
              <video
                :src="customVideoPreview"
                class="w-full h-24 object-cover"
                autoplay loop muted playsinline
              />
              <button
                @click="clearCustomMedia"
                class="absolute top-2 right-2 z-10 p-1 rounded-md bg-black/60 text-white hover:bg-red-600 transition-colors"
              >
                <Trash2 :size="14" />
              </button>
            </div>

            <!-- Replace button -->
            <button
              v-if="hasCustomMedia && !uploading"
              @click="fileInput?.click()"
              class="w-full text-xs text-txt-muted hover:text-txt-secondary py-1.5 rounded-md hover:bg-surface-3 transition-colors"
            >
              Replace with another file
            </button>

            <!-- Dim overlay slider (both image & video) -->
            <div v-if="hasCustomMedia && !uploading" class="space-y-1.5">
              <div class="flex items-center justify-between">
                <label class="text-xs text-txt-muted">Dim overlay</label>
                <span class="text-xs text-txt-muted tabular-nums">{{ Math.round(customOpacity * 100) }}%</span>
              </div>
              <input
                type="range" min="0.1" max="0.8" step="0.05"
                :value="customOpacity"
                @input="updateOpacity"
                class="w-full h-1.5 bg-surface-3 rounded-full appearance-none cursor-pointer
                       [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                       [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:cursor-pointer"
              />
            </div>

            <!-- Speed slider (video only) -->
            <div v-if="customMediaType === 'video' && !uploading" class="space-y-1.5">
              <div class="flex items-center justify-between">
                <label class="text-xs text-txt-muted">Playback speed</label>
                <span class="text-xs text-txt-muted tabular-nums">{{ Math.round(customVideoSpeed * 100) }}%</span>
              </div>
              <input
                type="range" min="0.2" max="1.0" step="0.05"
                :value="customVideoSpeed"
                @input="updateVideoSpeed"
                class="w-full h-1.5 bg-surface-3 rounded-full appearance-none cursor-pointer
                       [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                       [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:cursor-pointer"
              />
            </div>

            <input ref="fileInput" type="file" :accept="ALL_ACCEPT" class="hidden" @change="handleFileUpload" />
          </div>
        </div>

        <!-- Data Export -->
        <div>
          <h3 class="text-sm font-semibold text-txt-secondary uppercase tracking-wider mb-4">Data Export</h3>

          <div class="glass-card p-4 space-y-3">
            <p class="text-xs text-txt-secondary font-medium">Journal</p>
            <p class="text-[10px] text-txt-muted leading-relaxed">
              Download all journal entries with AI reflections. Markdown files include YAML frontmatter compatible with Obsidian.
            </p>

            <div class="flex gap-2">
              <button
                @click="exportJournal('markdown')"
                :disabled="exporting"
                class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium
                       bg-surface-3 text-txt-primary hover:bg-surface-4 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FileText :size="14" />
                Markdown (.zip)
              </button>
              <button
                @click="exportJournal('json')"
                :disabled="exporting"
                class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium
                       bg-surface-3 text-txt-primary hover:bg-surface-4 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FileJson :size="14" />
                JSON
              </button>
            </div>

            <!-- Export status -->
            <div v-if="exporting" class="flex items-center gap-2 text-xs text-txt-muted">
              <div class="w-3.5 h-3.5 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
              Exporting...
            </div>
            <p v-if="exportError" class="text-xs text-red-400">{{ exportError }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
