<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import {
  type ThemeId,
  getSavedTheme,
  getTheme,
  getCustomImage,
  getCustomOpacity,
  getCustomVideo,
  getCustomVideoSpeed,
  getCustomMediaType,
  getAIAmbientTheme,
  getAIAmbientInterval,
} from './background-themes'

const currentTheme = ref<ThemeId>(getSavedTheme())
const theme = computed(() => getTheme(currentTheme.value))
const hasVideo = computed(() => !!theme.value.video)
const DEFAULT_SPEED = 0.5

// Video refs for crossfade loop
const videoA = ref<HTMLVideoElement | null>(null)
const videoB = ref<HTMLVideoElement | null>(null)
const activeVideo = ref<'a' | 'b'>('a')
const videoLoaded = ref(false)

// Custom video
const customVideoRef = ref<HTMLVideoElement | null>(null)
const customVideoSrc = ref<string | null>(null)
const isCustomVideo = computed(() => currentTheme.value === 'custom' && getCustomMediaType() === 'video')

// AI Ambient wallpaper state
const aiCurrentImage = ref<string | null>(null)
const aiPreviousImage = ref<string | null>(null)
const aiShowCurrent = ref(true)
let aiPollTimer: ReturnType<typeof setInterval> | null = null
const isAIAmbient = computed(() => currentTheme.value === 'ai-ambient')

// Prefers-reduced-motion
const prefersReducedMotion = ref(false)
let motionQuery: MediaQueryList | null = null

onMounted(() => {
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion.value = motionQuery.matches
  motionQuery.addEventListener('change', (e) => { prefersReducedMotion.value = e.matches })
})

// Force playback rate — browsers reset it on load/play/loop
function enforceRate(video: HTMLVideoElement, rate?: number) {
  const target = rate ?? theme.value.speed ?? DEFAULT_SPEED
  if (video.playbackRate !== target) {
    video.playbackRate = target
  }
}

function handleRateEnforce(which: 'a' | 'b') {
  const video = which === 'a' ? videoA.value : videoB.value
  if (video) enforceRate(video)
}

// Crossfade: when active video nears end, fade to the other
function handleTimeUpdate(which: 'a' | 'b') {
  const video = which === 'a' ? videoA.value : videoB.value
  const other = which === 'a' ? videoB.value : videoA.value
  if (!video || !other || activeVideo.value !== which) return

  enforceRate(video)

  const remaining = video.duration - video.currentTime
  if (remaining < 1.5 && remaining > 0) {
    other.currentTime = 0
    other.play().catch(() => {})
    enforceRate(other)
    activeVideo.value = which === 'a' ? 'b' : 'a'
  }
}

// When theme changes, reset videos
function loadVideo(src: string) {
  videoLoaded.value = false
  activeVideo.value = 'a'
  nextTick(() => {
    if (videoA.value) {
      videoA.value.src = src
      videoA.value.load()
      videoA.value.playbackRate = theme.value.speed ?? DEFAULT_SPEED
      videoA.value.play().catch(() => {})
    }
    if (videoB.value) {
      videoB.value.src = src
      videoB.value.load()
      videoB.value.playbackRate = theme.value.speed ?? DEFAULT_SPEED
    }
  })
}

// Custom video: enforce user-chosen speed
function enforceCustomVideoRate() {
  if (customVideoRef.value) {
    enforceRate(customVideoRef.value, getCustomVideoSpeed())
  }
}

// Load custom video from IndexedDB
async function loadCustomVideo() {
  if (getCustomMediaType() !== 'video') {
    customVideoSrc.value = null
    return
  }
  const url = await getCustomVideo()
  customVideoSrc.value = url
  if (url) {
    nextTick(() => {
      if (customVideoRef.value) {
        customVideoRef.value.play().catch(() => {})
      }
    })
  }
}

// AI Ambient: start/stop scheduler and poll for new wallpapers
async function startAIAmbient() {
  const ambientTheme = getAIAmbientTheme()
  const interval = getAIAmbientInterval()

  try {
    // Start the ambient scheduler in ZugaVideo
    const res = await fetch('/api/video/ambient/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        theme: ambientTheme,
        interval_minutes: interval,
        size: '1920x1080',
        provider: 'flux_schnell',
      }),
    })
    if (res.ok) {
      const data = await res.json()
      if (data.current_wallpaper_data) {
        aiCurrentImage.value = data.current_wallpaper_data
      }
    }
  } catch { /* ZugaVideo may not be loaded */ }

  // Poll for updates
  aiPollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/video/ambient/status')
      if (!res.ok) return
      const data = await res.json()
      const newImage = data.current_wallpaper_data || data.current_wallpaper_url
      if (newImage && newImage !== aiCurrentImage.value) {
        // Crossfade: current becomes previous, new becomes current
        aiPreviousImage.value = aiCurrentImage.value
        aiCurrentImage.value = newImage
        aiShowCurrent.value = false
        // Trigger crossfade
        requestAnimationFrame(() => { aiShowCurrent.value = true })
      }
    } catch { /* silent */ }
  }, 15000)
}

function stopAIAmbient() {
  if (aiPollTimer) {
    clearInterval(aiPollTimer)
    aiPollTimer = null
  }
  // Don't stop the scheduler — other tabs may be using it
}

watch(currentTheme, (id) => {
  const t = getTheme(id)
  if (id === 'ai-ambient') {
    startAIAmbient()
  } else if (id === 'custom') {
    stopAIAmbient()
    loadCustomVideo()
  } else {
    stopAIAmbient()
    if (t.video && !prefersReducedMotion.value) {
      loadVideo(t.video)
    }
  }
}, { immediate: false })

// Initial load — watch videoA ref to ensure the element exists in DOM before loading
// (v-if="hasVideo" means the <video> may not be rendered on first onMounted tick)
watch(videoA, (el) => {
  if (el && theme.value.video && !prefersReducedMotion.value && !videoLoaded.value) {
    loadVideo(theme.value.video)
  }
})

onMounted(() => {
  if (currentTheme.value === 'ai-ambient') {
    startAIAmbient()
  } else if (currentTheme.value === 'custom') {
    loadCustomVideo()
  } else if (theme.value.video && !prefersReducedMotion.value && videoA.value) {
    loadVideo(theme.value.video)
  }
})

onUnmounted(() => {
  stopAIAmbient()
})

// Listen for theme change events from settings panel
function handleThemeChange(e: Event) {
  currentTheme.value = (e as CustomEvent).detail as ThemeId
}
onMounted(() => document.addEventListener('zugalife-theme-change', handleThemeChange))
onUnmounted(() => document.removeEventListener('zugalife-theme-change', handleThemeChange))
</script>

<template>
  <div class="fixed inset-0 z-0 overflow-hidden">
    <!-- Base layer: fallback gradient or solid dark -->
    <div
      class="absolute inset-0 transition-[background] duration-1000"
      :style="{
        background: theme.fallbackBg || '#0a0a0a',
      }"
    />

    <!-- Preset video layers (A and B for crossfade) -->
    <template v-if="hasVideo && !isCustomVideo && !prefersReducedMotion">
      <video
        ref="videoA"
        class="absolute inset-0 w-full h-full object-cover transition-opacity duration-[1500ms]"
        :class="activeVideo === 'a' ? 'opacity-100' : 'opacity-0'"
        autoplay
        loop
        muted
        playsinline
        @loadeddata="videoLoaded = true; handleRateEnforce('a')"
        @playing="handleRateEnforce('a')"
        @timeupdate="handleTimeUpdate('a')"
      />
      <video
        ref="videoB"
        class="absolute inset-0 w-full h-full object-cover transition-opacity duration-[1500ms]"
        :class="activeVideo === 'b' ? 'opacity-100' : 'opacity-0'"
        autoplay
        loop
        muted
        playsinline
        @loadeddata="handleRateEnforce('b')"
        @playing="handleRateEnforce('b')"
        @timeupdate="handleTimeUpdate('b')"
      />
    </template>

    <!-- Dark overlay for preset videos -->
    <div
      v-if="hasVideo && !isCustomVideo && theme.overlay && theme.overlay > 0"
      class="absolute inset-0"
      :style="{ background: `rgba(0, 0, 0, ${theme.overlay})` }"
    />

    <!-- AI Ambient wallpaper (crossfade between two images) -->
    <template v-if="isAIAmbient">
      <div
        v-if="aiPreviousImage"
        class="absolute inset-0 bg-cover bg-center bg-no-repeat transition-opacity duration-[3000ms]"
        :class="aiShowCurrent ? 'opacity-0' : 'opacity-100'"
        :style="{ backgroundImage: `url(${aiPreviousImage})` }"
      />
      <div
        v-if="aiCurrentImage"
        class="absolute inset-0 bg-cover bg-center bg-no-repeat transition-opacity duration-[3000ms]"
        :class="aiShowCurrent ? 'opacity-100' : 'opacity-0'"
        :style="{ backgroundImage: `url(${aiCurrentImage})` }"
      />
      <!-- Dark overlay for AI wallpapers -->
      <div
        class="absolute inset-0"
        :style="{ background: `rgba(0, 0, 0, ${theme.overlay || 0.25})` }"
      />
    </template>

    <!-- Custom Image -->
    <div
      v-if="currentTheme === 'custom' && getCustomMediaType() === 'image' && getCustomImage()"
      class="absolute inset-0 bg-cover bg-center bg-no-repeat"
      :style="{
        backgroundImage: `url(${getCustomImage()})`,
        opacity: getCustomOpacity(),
      }"
    />

    <!-- Custom Video -->
    <template v-if="isCustomVideo && customVideoSrc && !prefersReducedMotion">
      <video
        ref="customVideoRef"
        :src="customVideoSrc"
        class="absolute inset-0 w-full h-full object-cover"
        autoplay
        loop
        muted
        playsinline
        @loadeddata="enforceCustomVideoRate"
        @playing="enforceCustomVideoRate"
        @timeupdate="enforceCustomVideoRate"
      />
      <!-- Dim overlay for custom video -->
      <div
        class="absolute inset-0"
        :style="{ background: `rgba(0, 0, 0, ${getCustomOpacity()})` }"
      />
    </template>
  </div>
</template>
