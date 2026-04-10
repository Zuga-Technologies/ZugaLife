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
import { TraderThemeBridge } from './TraderThemeBridge'
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
let bridge: ThemeBridge | TraderThemeBridge | null = null

// Sandbox flags — allow-scripts ONLY. No allow-same-origin, no allow-forms.
const sandboxFlags = 'allow-scripts'

// Build the srcdoc that gets injected into the iframe
const srcdoc = computed(() => {
  const t = props.theme
  if (!t.html || !t.js) return ''

  // CSP meta tag — blocks all network requests from inside the iframe
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src https: data:; font-src https:;">`

  // Base theme styles — inherits parent's CSS vars via computed style extraction
  // Note: iframes are sandboxed so they can't access parent CSS vars directly.
  // We inject the resolved RGB values from the parent's computed theme.
  const rs = getComputedStyle(document.documentElement)
  const cv = (name: string) => rs.getPropertyValue(`--${name}`).trim() || '163 163 163'
  const baseStyles = `
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: transparent;
      color: rgb(${cv('txt-secondary')});
      font-family: ${cv('font-sans') || "'Inter', system-ui, sans-serif"};
      font-size: 13px;
      line-height: 1.6;
      overflow-x: hidden;
      padding: 12px;
      max-width: 100%;
    }
    a { color: rgb(${cv('color-info')}); text-decoration: none; }
    a:hover { text-decoration: underline; }
    img, canvas, svg { max-width: 100%; height: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 4px 8px; text-align: left; border-bottom: 1px solid rgba(${cv('bdr')}, 0.2); }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(${cv('txt-muted')}, 0.3); border-radius: 3px; }
    @media (max-width: 480px) {
      body { font-size: 12px; padding: 8px; }
      h1, h2, h3 { font-size: clamp(14px, 4vw, 20px); }
    }
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

  const meta = {
    themeId: props.theme.id,
    title: props.theme.title,
    studio: props.studio,
  }

  // Select bridge based on studio — each studio has its own permission allowlist
  const BridgeClass = props.studio === 'trader' ? TraderThemeBridge : ThemeBridge
  bridge = new BridgeClass(iframeRef.value, props.theme.permissions, meta)
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
  background: rgb(var(--surface-1) / 0.6);
  border: 1px solid rgb(var(--bdr) / 0.3);
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
  background: rgb(var(--surface-0) / 0.5);
  border-bottom: 1px solid rgb(var(--bdr) / 0.2);
  min-height: 30px;
  flex-shrink: 0;
}

.theme-title {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--txt-primary));
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
  color: rgb(var(--txt-secondary));
  transition: all 0.15s;
}
.theme-btn:hover {
  background: rgb(var(--txt-muted) / 0.2);
  color: rgb(var(--txt-primary));
}
.theme-btn-remove:hover { color: rgb(var(--color-danger)); }
.theme-btn-retry {
  margin-top: 8px;
  color: rgb(var(--color-info));
  border: 1px solid rgb(var(--color-info) / 0.3);
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
  color: rgb(var(--txt-muted));
  font-size: 13px;
  gap: 8px;
  flex: 1;
}

.theme-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgb(var(--txt-muted) / 0.3);
  border-top-color: rgb(var(--accent));
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.theme-error-msg { color: rgb(var(--color-danger)); }

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
