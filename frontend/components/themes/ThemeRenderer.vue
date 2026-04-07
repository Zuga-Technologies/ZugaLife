<template>
  <div class="theme-renderer" :class="{ 'theme-loading': loading, 'theme-error': error }">
    <!-- Title bar -->
    <div class="theme-title-bar" v-if="showTitleBar">
      <span class="theme-title">{{ theme.title }}</span>
      <div class="theme-actions">
        <button
          v-if="removable"
          class="theme-btn theme-btn-remove"
          title="Remove theme"
          @click="$emit('remove')"
        >
          &times;
        </button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="theme-placeholder">
      <div class="theme-spinner" />
      <span>Loading theme...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="theme-placeholder theme-error-msg">
      <span>{{ error }}</span>
      <button class="theme-btn theme-btn-retry" @click="renderTheme">Retry</button>
    </div>

    <!-- Sandboxed iframe -->
    <iframe
      v-show="!loading && !error"
      ref="iframeRef"
      :sandbox="sandboxFlags"
      :srcdoc="srcdoc"
      referrerpolicy="no-referrer"
      loading="lazy"
      class="theme-iframe"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { THEME_SDK_SOURCE } from './ThemeSDK'
import { ThemeBridge } from './ThemeBridge'
import type { ThemePermission } from './ThemeBridge'

export interface ThemeData {
  id: string
  title: string
  html: string
  css?: string | null
  js: string
  permissions: ThemePermission[]
}

const props = withDefaults(defineProps<{
  theme: ThemeData
  studio?: string
  showTitleBar?: boolean
  removable?: boolean
}>(), {
  studio: 'life',
  showTitleBar: true,
  removable: true,
})

defineEmits<{
  remove: []
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
let bridge: ThemeBridge | null = null

// Sandbox flags — allow-scripts ONLY. No allow-same-origin, no allow-forms.
const sandboxFlags = 'allow-scripts'

// Build the srcdoc that gets injected into the iframe
const srcdoc = computed(() => {
  const t = props.theme
  if (!t.html || !t.js) return ''

  // CSP meta tag — blocks all network requests from inside the iframe
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src https: data:; font-src https:;">`

  // Base dark theme styles
  const baseStyles = `
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: transparent;
      color: #cbd5e1;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      font-size: 13px;
      line-height: 1.6;
      overflow-x: hidden;
      padding: 12px;
    }
    a { color: #60a5fa; text-decoration: none; }
    a:hover { text-decoration: underline; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(100,116,139,0.3); border-radius: 3px; }
  `

  const SC = '<' + '/script>'
  const doc = [
    '<!DOCTYPE html><html lang="en"><head>',
    csp,
    `<style>${baseStyles}<` + '/style>',
    t.css ? `<style>${t.css}<` + '/style>' : '',
    '<' + '/head><body>',
    t.html,
    `<script>${THEME_SDK_SOURCE}${SC}`,
    '<script>',
    'try {', t.js, '} catch (err) {',
    `document.body.innerHTML = '<div style="color:#f87171;padding:16px;">'`,
    `+ '<strong>Theme Error<` + `/strong><br>' + err.message + '<` + `/div>'`,
    '}',
    SC,
    '<' + '/body><' + '/html>',
  ]
  return doc.join('\n')
})

function onIframeLoad() {
  loading.value = false
  setupBridge()
}

function onIframeError() {
  loading.value = false
  error.value = 'Failed to load theme'
}

function setupBridge() {
  // Clean up previous bridge
  if (bridge) {
    bridge.destroy()
    bridge = null
  }

  if (!iframeRef.value) return

  bridge = new ThemeBridge(
    iframeRef.value,
    props.theme.permissions,
    {
      themeId: props.theme.id,
      title: props.theme.title,
      studio: props.studio,
    }
  )
}

function renderTheme() {
  error.value = null
  loading.value = true
  // Force re-render by toggling the srcdoc
  if (iframeRef.value) {
    iframeRef.value.srcdoc = srcdoc.value
  }
}

// Re-render when theme code changes
watch(() => props.theme, () => {
  renderTheme()
}, { deep: true })

onMounted(() => {
  if (srcdoc.value) {
    loading.value = true
  } else {
    loading.value = false
    error.value = 'Theme has no content'
  }
})

onBeforeUnmount(() => {
  if (bridge) {
    bridge.destroy()
    bridge = null
  }
})
</script>

<style scoped>
.theme-renderer {
  background: rgba(30, 35, 50, 0.6);
  border: 1px solid rgba(80, 90, 120, 0.3);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.theme-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: rgba(15, 18, 30, 0.5);
  border-bottom: 1px solid rgba(80, 90, 120, 0.2);
  min-height: 30px;
  flex-shrink: 0;
}

.theme-title {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.theme-actions {
  display: flex;
  gap: 4px;
}

.theme-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: #94a3b8;
  transition: all 0.15s;
}
.theme-btn:hover {
  background: rgba(100, 116, 139, 0.2);
  color: #e2e8f0;
}
.theme-btn-remove:hover { color: #f87171; }
.theme-btn-retry {
  margin-top: 8px;
  color: #60a5fa;
  border: 1px solid rgba(96, 165, 250, 0.3);
  padding: 4px 12px;
}

.theme-iframe {
  flex: 1;
  width: 100%;
  border: none;
  background: transparent;
  min-height: 100px;
}

.theme-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #64748b;
  font-size: 13px;
  gap: 8px;
  flex: 1;
}

.theme-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(100, 116, 139, 0.3);
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.theme-error-msg { color: #f87171; }

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
