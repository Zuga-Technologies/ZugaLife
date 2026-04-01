<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@core/auth/store'
import { getToken } from '@core/api/client'
import { Settings, Leaf, LogOut, ChevronDown } from 'lucide-vue-next'
import BackgroundTheme from './BackgroundTheme.vue'
import SettingsPanel from './SettingsPanel.vue'

const auth = useAuthStore()
const email = ref('')
const submitting = ref(false)
const showSettings = ref(false)
const showDropdown = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

// Optimistic auth: if token exists, assume authenticated immediately.
// The background checkAuth() will redirect to login if the token is invalid.
const hasToken = ref(!!getToken())

// When auth finishes loading and user is null, token was invalid — show login
watch(() => auth.loading, (loading) => {
  if (!loading && !auth.isAuthenticated) {
    hasToken.value = false
  }
})

onMounted(() => {
  if (hasToken.value) {
    auth.checkAuth()
  }
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

function handleClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    showDropdown.value = false
  }
}

async function handleLogin() {
  if (!email.value.trim() || submitting.value) return
  submitting.value = true
  try {
    await auth.login(email.value.trim())
  } catch {
    // Error is set in the store
  } finally {
    submitting.value = false
  }
}

async function handleLogout() {
  showDropdown.value = false
  await auth.logout()
}

function openSettings() {
  showDropdown.value = false
  showSettings.value = true
}

function goHome() {
  document.dispatchEvent(new Event('zugalife-go-home'))
}
</script>

<template>
  <div class="min-h-screen">
    <!-- Animated background layer (includes base color) -->
    <BackgroundTheme />

    <!-- Authenticated (or optimistically assumed via token): nav + router-view -->
    <template v-if="auth.isAuthenticated || (hasToken && auth.loading)">
      <nav class="fixed top-0 left-0 right-0 z-50 h-14 bg-surface-0/80 backdrop-blur-md border-b border-bdr flex items-center px-6">
        <button
          @click="goHome"
          class="flex items-center gap-2 mr-8 transition-opacity hover:opacity-80"
        >
          <Leaf :size="20" class="text-accent" />
          <span class="text-sm font-semibold text-txt-primary tracking-wide">ZugaLife</span>
        </button>
        <div class="flex-1" />

        <!-- User dropdown (hidden during optimistic load before user data arrives) -->
        <div v-if="auth.user" ref="dropdownRef" class="relative">
          <button
            @click="showDropdown = !showDropdown"
            class="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors hover:bg-surface-3/50"
          >
            <span class="text-sm text-txt-secondary">{{ auth.user?.email }}</span>
            <ChevronDown
              :size="14"
              class="text-txt-muted transition-transform duration-200"
              :class="{ 'rotate-180': showDropdown }"
            />
          </button>

          <!-- Dropdown menu -->
          <transition name="dropdown">
            <div
              v-if="showDropdown"
              class="absolute right-0 mt-1.5 w-48 rounded-xl bg-surface-1 border border-bdr shadow-xl shadow-black/20 overflow-hidden"
            >
              <button
                @click="openSettings"
                class="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-txt-secondary hover:text-txt-primary hover:bg-surface-3/50 transition-colors"
              >
                <Settings :size="15" class="text-txt-muted" />
                Settings
              </button>
              <div class="border-t border-bdr" />
              <button
                @click="handleLogout"
                class="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-txt-secondary hover:text-red-400 hover:bg-surface-3/50 transition-colors"
              >
                <LogOut :size="15" class="text-txt-muted" />
                Logout
              </button>
            </div>
          </transition>
        </div>
      </nav>
      <main class="pt-16 relative z-10">
        <router-view />
      </main>
    </template>

    <!-- Not authenticated: login form (only after auth check completes or no token) -->
    <template v-else-if="!auth.loading && !hasToken">
      <div class="min-h-screen flex items-center justify-center px-4">
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div class="w-[600px] h-[600px] rounded-full bg-accent/[0.03] blur-3xl" />
        </div>

        <div class="relative glass-card w-full max-w-sm p-8 animate-slide-up">
          <div class="flex flex-col items-center mb-8">
            <div class="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center mb-4 animate-pulse-glow">
              <Leaf :size="24" class="text-accent" />
            </div>
            <h1 class="text-xl font-semibold text-txt-primary">ZugaLife</h1>
            <p class="text-sm text-txt-muted mt-1">Sign in to continue</p>
          </div>

          <form @submit.prevent="handleLogin" class="space-y-4">
            <div>
              <label for="email" class="block text-sm font-medium text-txt-secondary mb-1.5">
                Email
              </label>
              <input
                id="email"
                v-model="email"
                type="email"
                placeholder="you@example.com"
                required
                autocomplete="email"
                class="input-field"
              />
            </div>

            <p v-if="auth.error" class="text-sm text-red-400">
              {{ auth.error }}
            </p>

            <button
              type="submit"
              :disabled="!email.trim() || submitting"
              class="btn-primary w-full"
            >
              <span v-if="submitting" class="inline-flex items-center gap-2">
                <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Signing in...
              </span>
              <span v-else>Sign in</span>
            </button>
          </form>

          <p class="text-center text-xs text-txt-muted mt-6">
            Dev mode — any email works
          </p>
        </div>
      </div>
    </template>

    <!-- Settings panel overlay -->
    <transition name="fade">
      <SettingsPanel v-if="showSettings" @close="showSettings = false" />
    </transition>
  </div>
</template>

<style scoped>
.dropdown-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.dropdown-leave-active {
  transition: opacity 0.1s ease, transform 0.1s ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}
</style>
