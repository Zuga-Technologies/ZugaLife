/**
 * useNotifications — Push notification registration, subscription, and preferences.
 *
 * Handles: service worker registration, permission flow, VAPID subscription,
 * backend sync, and preference management.
 */
import { ref, computed } from 'vue'
import { api } from '@core/api/client'

// ---------------------------------------------------------------------------
// State (singleton across components)
// ---------------------------------------------------------------------------

const permission = ref<NotificationPermission>(
  typeof Notification !== 'undefined' ? Notification.permission : 'default'
)
const isSubscribed = ref(false)
const isLoading = ref(false)
const swRegistration = ref<ServiceWorkerRegistration | null>(null)
const promptDismissed = ref(false)
const preferences = ref<NotifPreferences | null>(null)

// Don't ask on first visit — wait for a meaningful moment
const PROMPT_STORAGE_KEY = 'zugalife-notif-prompt-dismissed'
const SUBSCRIBED_KEY = 'zugalife-notif-subscribed'

interface NotifPreferences {
  enabled: boolean
  quiet_start: string | null
  quiet_end: string | null
  reminder_hour: number
  streak_warnings: boolean
  daily_nudges: boolean
  milestone_alerts: boolean
}

// ---------------------------------------------------------------------------
// Service Worker + Subscription
// ---------------------------------------------------------------------------

async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  try {
    const reg = await navigator.serviceWorker.register('/sw-notifications.js', { scope: '/' })
    swRegistration.value = reg
    return reg
  } catch (err) {
    console.warn('SW registration failed:', err)
    return null
  }
}

async function subscribe(): Promise<boolean> {
  isLoading.value = true
  try {
    // 1. Register SW if not already
    let reg = swRegistration.value
    if (!reg) {
      reg = await registerServiceWorker()
      if (!reg) return false
    }

    // 2. Request permission
    const perm = await Notification.requestPermission()
    permission.value = perm
    if (perm !== 'granted') return false

    // 3. Get VAPID public key from backend
    const { vapid_public_key } = await api.get<{ vapid_public_key: string }>(
      '/api/life/notifications/vapid-key'
    )

    // 4. Subscribe to push manager
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid_public_key),
    })

    const keys = sub.toJSON().keys || {}

    // 5. Send subscription to backend
    await api.post('/api/life/notifications/subscribe', {
      endpoint: sub.endpoint,
      p256dh: keys.p256dh || '',
      auth: keys.auth || '',
    })

    isSubscribed.value = true
    localStorage.setItem(SUBSCRIBED_KEY, '1')
    return true
  } catch (err) {
    console.warn('Push subscription failed:', err)
    return false
  } finally {
    isLoading.value = false
  }
}

async function unsubscribe(): Promise<void> {
  isLoading.value = true
  try {
    // Unsubscribe from push manager
    const reg = swRegistration.value || await navigator.serviceWorker?.ready
    if (reg) {
      const sub = await reg.pushManager.getSubscription()
      if (sub) await sub.unsubscribe()
    }

    // Tell backend
    await api.delete('/api/life/notifications/unsubscribe')
    isSubscribed.value = false
    localStorage.removeItem(SUBSCRIBED_KEY)
  } catch (err) {
    console.warn('Unsubscribe failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Preferences
// ---------------------------------------------------------------------------

async function loadPreferences(): Promise<void> {
  try {
    preferences.value = await api.get<NotifPreferences>('/api/life/notifications/preferences')
  } catch { /* non-critical */ }
}

async function savePreferences(prefs: Partial<NotifPreferences>): Promise<void> {
  try {
    const current = preferences.value || {
      enabled: true, quiet_start: null, quiet_end: null,
      reminder_hour: 9, streak_warnings: true, daily_nudges: true, milestone_alerts: true,
    }
    const merged = { ...current, ...prefs }
    preferences.value = await api.put<NotifPreferences>('/api/life/notifications/preferences', merged)
  } catch (err) {
    console.warn('Failed to save notification preferences:', err)
  }
}

// ---------------------------------------------------------------------------
// Permission prompt logic
// ---------------------------------------------------------------------------

function dismissPrompt() {
  promptDismissed.value = true
  localStorage.setItem(PROMPT_STORAGE_KEY, Date.now().toString())
}

function shouldShowPrompt(): boolean {
  // Never show if already subscribed or denied
  if (isSubscribed.value) return false
  if (permission.value === 'denied') return false
  if (promptDismissed.value) return false

  // Check if previously dismissed (re-ask after 7 days)
  const dismissed = localStorage.getItem(PROMPT_STORAGE_KEY)
  if (dismissed) {
    const dismissedAt = parseInt(dismissed, 10)
    const sevenDays = 7 * 24 * 60 * 60 * 1000
    if (Date.now() - dismissedAt < sevenDays) return false
  }

  return true
}

// ---------------------------------------------------------------------------
// Init — check current state
// ---------------------------------------------------------------------------

async function init(): Promise<void> {
  if (typeof Notification !== 'undefined') {
    permission.value = Notification.permission
  }

  // Check if we think we're subscribed
  if (localStorage.getItem(SUBSCRIBED_KEY) === '1') {
    isSubscribed.value = true

    // Verify SW is still registered
    if ('serviceWorker' in navigator) {
      try {
        const reg = await navigator.serviceWorker.ready
        swRegistration.value = reg
        const sub = await reg.pushManager.getSubscription()
        if (!sub) {
          // Subscription lost (browser cleared data) — re-subscribe silently
          isSubscribed.value = false
          localStorage.removeItem(SUBSCRIBED_KEY)
        }
      } catch { /* SW not ready yet */ }
    }
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export function useNotifications() {
  return {
    // State
    permission: computed(() => permission.value),
    isSubscribed: computed(() => isSubscribed.value),
    isLoading: computed(() => isLoading.value),
    preferences: computed(() => preferences.value),

    // Actions
    init,
    subscribe,
    unsubscribe,
    loadPreferences,
    savePreferences,
    shouldShowPrompt,
    dismissPrompt,
  }
}
