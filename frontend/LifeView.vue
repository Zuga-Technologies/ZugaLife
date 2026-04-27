<script setup lang="ts">
import { ref, defineAsyncComponent, onMounted, onUnmounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useLifeShared } from './composables/useLifeShared'
import { useOnboardingStore } from '@zugaapp/stores/onboarding'
import { useNotifications } from './composables/useNotifications'
import { ArrowLeft, AlertTriangle, Zap } from 'lucide-vue-next'
import BackgroundTheme from './BackgroundTheme.vue'
import CelebrationOverlay from './components/CelebrationOverlay.vue'
import LifeOnboarding from './components/LifeOnboarding.vue'
import BreathColdOpen from './components/BreathColdOpen.vue'
import SettingsPanel from './SettingsPanel.vue'

// ── Lazy-loaded tab components ─────────────────────────────────
const DashboardTab = defineAsyncComponent(() => import('./tabs/DashboardTab.vue'))
const JournalTab = defineAsyncComponent(() => import('./tabs/JournalTab.vue'))
const HabitsTab = defineAsyncComponent(() => import('./tabs/HabitsTab.vue'))
const GoalsTab = defineAsyncComponent(() => import('./tabs/GoalsTab.vue'))
const MeditateTab = defineAsyncComponent(() => import('./tabs/MeditateTab.vue'))
const TherapistTab = defineAsyncComponent(() => import('./tabs/TherapistTab.vue'))

// ── Props ──────────────────────────────────────────────────────
const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

// ── Shared state ───────────────────────────────────────────────
const {
  showBillingPrompt,
  billingPromptFeature,
  showBillingPacks,
  tokenStore,
  goToBilling,
  closeBillingPrompt,
  showServiceError,
  serviceErrorTitle,
  serviceErrorMessage,
  serviceErrorRetryFn,
  closeServiceError,
  retryFromServiceError,
} = useLifeShared()

const notif = useNotifications()
const onboarding = useOnboardingStore()

// ── Tabs ───────────────────────────────────────────────────────
type Tab = 'dashboard' | 'journal' | 'habits' | 'goals' | 'meditate' | 'therapist'
const activeTab = ref<Tab>('dashboard')

const moduleLabels: Record<Exclude<Tab, 'dashboard'>, string> = {
  journal: 'Journal',
  habits: 'Habits',
  goals: 'Goals',
  meditate: 'Meditate',
  therapist: 'Wellness Bot',
}

// ── Settings ───────────────────────────────────────────────────
const showSettings = ref(false)

// ── Therapist session guard ────────────────────────────────────
const therapistRef = ref<InstanceType<typeof TherapistTab> | null>(null)
const showTherapistLeaveWarning = ref(false)
const pendingTab = ref<Tab | null>(null)
const pendingRouteLeave = ref<(() => void) | null>(null)

function isTherapistActive(): boolean {
  const t = therapistRef.value
  return !!(t?.therapistSessionActive && t?.therapistMessages?.length >= 2)
}

function navigateTo(tab: Tab) {
  if (tab !== 'therapist' && isTherapistActive()) {
    pendingTab.value = tab
    pendingRouteLeave.value = null
    showTherapistLeaveWarning.value = true
    return
  }
  activeTab.value = tab
}

function confirmTherapistLeave() {
  showTherapistLeaveWarning.value = false
  if (therapistRef.value) {
    therapistRef.value.therapistSessionActive = false
    therapistRef.value.therapistMessages = []
  }
  if (pendingTab.value) {
    activeTab.value = pendingTab.value
    pendingTab.value = null
  }
  if (pendingRouteLeave.value) {
    pendingRouteLeave.value()
    pendingRouteLeave.value = null
  }
}

function cancelTherapistLeave() {
  showTherapistLeaveWarning.value = false
  pendingTab.value = null
  pendingRouteLeave.value = null
}

// Guard: leaving ZugaLife entirely (router navigation to another studio)
onBeforeRouteLeave((_to, _from, next) => {
  if (isTherapistActive()) {
    pendingTab.value = null
    pendingRouteLeave.value = () => next()
    showTherapistLeaveWarning.value = true
    next(false)
  } else {
    next()
  }
})

// Guard: browser refresh / close tab
function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (isTherapistActive()) {
    e.preventDefault()
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnloadHandler))

// ── Breath cold-open (once per UTC day, dismissable) ───────────
// Skipped automatically when LifeOnboarding is showing — first-time
// users get the onboarding's own intro instead of two welcomes back-to-back.
//
// Gate is now CROSS-DEVICE: the server stores last_breath_date in
// LifeUserSettings, so completing on phone skips the prompt on desktop
// (and vice-versa). localStorage stays as a fast-path cache so the
// component doesn't render then immediately disappear on second visits.
import { api } from '@core/api/client'
const BREATH_KEY = 'zugalife.breathDate'
const showBreath = ref(false)
function todayUtcDate(): string {
  return new Date().toISOString().slice(0, 10)
}
async function maybeShowBreath() {
  if (onboarding.showLifeOnboarding) return  // first-time user — onboarding handles it
  const today = todayUtcDate()
  // Fast-path: localStorage knows we did it today, skip immediately.
  if (localStorage.getItem(BREATH_KEY) === today) return
  // Slow-path: ask the server in case the user did it on another device.
  try {
    const res = await api.get<{ done_today: boolean }>('/api/life/breath/today')
    if (res.done_today) {
      localStorage.setItem(BREATH_KEY, today)  // cache server answer
      return
    }
  } catch { /* network blip — fall through and show */ }
  showBreath.value = true
}
function onBreathDone() {
  localStorage.setItem(BREATH_KEY, todayUtcDate())
  showBreath.value = false
  // Fire-and-forget — server gate so other devices skip too.
  void api.post('/api/life/breath/done').catch(() => { /* non-critical */ })
}

// ── Onboarding ─────────────────────────────────────────────────
function onLifeOnboardingComplete(recommendedTab?: string) {
  onboarding.completeLifeOnboarding()
  const tabMap: Record<string, Tab> = {
    mood: 'dashboard',
    journal: 'journal',
    habits: 'habits',
    meditate: 'meditate',
  }
  if (recommendedTab && tabMap[recommendedTab]) {
    activeTab.value = tabMap[recommendedTab]
  }
}

// ── Settings open from ZugaApp dropdown ────────────────────────
function handleOpenSettings() { if (!props.embedded) showSettings.value = true }
onMounted(() => document.addEventListener('zugalife-open-settings', handleOpenSettings))
onUnmounted(() => document.removeEventListener('zugalife-open-settings', handleOpenSettings))

// ── Logo home ──────────────────────────────────────────────────
function handleLogoHome() { navigateTo('dashboard') }
onMounted(() => document.addEventListener('zugalife-go-home', handleLogoHome))
onUnmounted(() => document.removeEventListener('zugalife-go-home', handleLogoHome))

// ── Theme navigation events (themes can request tab changes) ──
function handleThemeNavigate(e: Event) {
  const to = (e as CustomEvent).detail?.to
  if (to && ['dashboard', 'journal', 'habits', 'goals', 'meditate', 'therapist'].includes(to)) {
    navigateTo(to as Tab)
  }
}
onMounted(() => window.addEventListener('zugatheme:navigate', handleThemeNavigate as EventListener))
onUnmounted(() => window.removeEventListener('zugatheme:navigate', handleThemeNavigate as EventListener))

// ── Init ───────────────────────────────────────────────────────
onMounted(async () => {
  notif.init()
  await onboarding.checkLifeOnboarding()
  maybeShowBreath()
})
</script>

<template>
  <div>
    <!-- Animated background layer -->
    <BackgroundTheme />
    <!-- Celebration overlay (toasts, confetti, modals) -->
    <CelebrationOverlay />
    <!-- Studio onboarding (first visit only) -->
    <LifeOnboarding v-if="onboarding.showLifeOnboarding" @complete="onLifeOnboardingComplete" />
    <!-- Daily breath cold-open (once per UTC day, skippable, first-time users see onboarding instead) -->
    <BreathColdOpen v-if="showBreath" @complete="onBreathDone" @skip="onBreathDone" />

    <div
      class="relative z-10 mx-auto py-10 animate-fade-in"
      :class="activeTab !== 'dashboard'
        ? 'max-w-4xl px-6 mx-4 sm:mx-auto rounded-2xl bg-surface-0/80 backdrop-blur-md border border-white/[0.04]'
        : 'max-w-7xl px-6'"
    >

    <!-- Back nav + module label (shown on non-dashboard tabs) -->
    <div v-if="activeTab !== 'dashboard'" class="flex items-center gap-3 mb-6">
      <button
        @click="navigateTo('dashboard')"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-txt-muted transition-colors hover:text-txt-primary hover:bg-surface-3/50"
      >
        <ArrowLeft :size="16" />
        <span>Back</span>
      </button>
      <span class="text-sm font-semibold text-txt-primary">{{ moduleLabels[activeTab as Exclude<Tab, 'dashboard'>] }}</span>
      <div class="flex-1" />
    </div>

    <!-- ===== TAB CONTENT (lazy-loaded, only one mounted at a time) ===== -->
    <div class="contain-content">
      <DashboardTab
        v-if="activeTab === 'dashboard'"
        :embedded="embedded"
        @navigate="navigateTo($event as Tab)"
        @open-settings="showSettings = true"
      />

      <JournalTab v-if="activeTab === 'journal'" />
      <HabitsTab v-if="activeTab === 'habits'" />
      <GoalsTab v-if="activeTab === 'goals'" />
      <MeditateTab v-if="activeTab === 'meditate'" />
      <TherapistTab
        v-if="activeTab === 'therapist'"
        ref="therapistRef"
      />
    </div>

    <!-- Therapist session leave warning -->
    <transition name="fade">
      <div v-if="showTherapistLeaveWarning" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div class="bg-surface-1 border border-white/[0.08] rounded-2xl p-6 max-w-sm mx-4 shadow-xl">
          <div class="flex items-center gap-3 mb-3">
            <AlertTriangle class="w-5 h-5 text-accent shrink-0" />
            <h3 class="text-lg font-semibold text-txt-primary">Active session</h3>
          </div>
          <p class="text-sm text-txt-secondary mb-5">
            You have an active therapy session. Leaving will reset it and your conversation will be lost.
          </p>
          <div class="flex gap-3 justify-end">
            <button
              @click="cancelTherapistLeave"
              class="px-4 py-2 text-sm font-medium text-txt-secondary hover:text-txt-primary rounded-lg border border-white/[0.08] hover:bg-surface-2 transition-colors"
            >
              Stay
            </button>
            <button
              @click="confirmTherapistLeave"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-500 rounded-lg transition-colors"
            >
              Leave &amp; reset
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Settings panel overlay -->
    <transition name="fade">
      <SettingsPanel v-if="showSettings" @close="showSettings = false" />
    </transition>
    </div>

    <!-- Billing Prompt Modal -->
    <Teleport to="body">
      <div v-if="showBillingPrompt" class="fixed inset-0 z-[999] flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="closeBillingPrompt">
        <div class="glass-card p-6 max-w-md mx-4 border border-accent/30 text-center">
          <div class="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-4">
            <Zap :size="24" class="text-accent" />
          </div>

          <!-- Step 1: Prompt -->
          <template v-if="!showBillingPacks">
            <h3 class="text-lg font-semibold text-txt-primary mb-2">Tokens Required</h3>
            <p class="text-sm text-txt-secondary mb-4">
              <strong>{{ billingPromptFeature }}</strong> requires ZugaTokens. Add tokens to continue using AI-powered features.
            </p>
            <div class="flex gap-3 justify-center">
              <button @click="closeBillingPrompt" class="px-4 py-2 text-sm text-txt-muted hover:text-txt-primary transition-colors">
                Later
              </button>
              <button @click="goToBilling" class="px-4 py-2 text-sm font-medium bg-accent text-black rounded-lg hover:bg-accent-bright transition-colors">
                Get Tokens
              </button>
            </div>
          </template>

          <!-- Step 2: Purchase packs -->
          <template v-else>
            <h3 class="text-lg font-semibold text-txt-primary mb-1">Buy ZugaTokens</h3>
            <p class="text-xs text-txt-muted mb-4">One-time packs — tokens never expire.</p>

            <div class="space-y-2 mb-4 text-left" v-if="tokenStore.packs.length">
              <button
                v-for="pack in tokenStore.packs"
                :key="pack.id"
                @click="tokenStore.buyPack(pack.id)"
                :disabled="tokenStore.purchaseLoading !== null"
                class="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-bdr hover:border-accent/50 hover:bg-accent/5 transition-all"
                :class="{ 'ring-2 ring-accent': pack.id === 'best_value' }"
              >
                <div class="flex items-center gap-3">
                  <span class="text-lg font-bold text-accent">{{ pack.tokens.toLocaleString() }}</span>
                  <span class="text-xs text-txt-muted">tokens</span>
                </div>
                <div class="flex items-center gap-2">
                  <span v-if="pack.id === 'best_value'" class="text-[10px] font-semibold uppercase tracking-wider text-accent bg-accent/10 px-2 py-0.5 rounded-full">Best Value</span>
                  <span class="text-sm font-semibold text-txt-primary">
                    ${{ (pack.price_cents / 100).toFixed(2) }}
                  </span>
                </div>
              </button>
            </div>
            <div v-else class="py-6 text-sm text-txt-muted">Loading packs...</div>

            <!-- Subscription tiers -->
            <div v-if="tokenStore.tiers.length" class="mb-4">
              <p class="text-xs text-txt-muted mb-3 uppercase tracking-wider font-semibold">Or subscribe monthly</p>
              <div class="grid grid-cols-3 gap-2">
                <button
                  v-for="tier in tokenStore.tiers"
                  :key="tier.id"
                  @click="tokenStore.subscribeTier(tier.id)"
                  :disabled="tokenStore.purchaseLoading !== null"
                  class="flex flex-col items-center px-3 py-3 rounded-xl border border-bdr hover:border-accent/50 hover:bg-accent/5 transition-all"
                >
                  <span class="text-xs font-semibold text-txt-primary capitalize">{{ tier.id }}</span>
                  <span class="text-lg font-bold text-accent mt-1">{{ tier.tokens_per_month.toLocaleString() }}</span>
                  <span class="text-[10px] text-txt-muted">tokens/mo</span>
                  <span class="text-xs font-semibold text-txt-secondary mt-1">${{ (tier.price_cents / 100).toFixed(0) }}/mo</span>
                </button>
              </div>
            </div>

            <!-- Error message -->
            <p v-if="tokenStore.purchaseError" class="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 mb-3">
              {{ tokenStore.purchaseError }}
            </p>

            <button @click="closeBillingPrompt" class="w-full py-2.5 rounded-lg text-sm text-txt-muted hover:text-txt-primary border border-bdr hover:bg-surface-2 transition-colors">
              Close
            </button>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Service Error Modal -->
    <Teleport to="body">
      <div v-if="showServiceError" class="fixed inset-0 z-[999] flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="closeServiceError">
        <div class="glass-card p-6 max-w-md mx-4 border border-red-500/30 text-center">
          <div class="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle :size="24" class="text-red-400" />
          </div>
          <h3 class="text-lg font-semibold text-txt-primary mb-2">{{ serviceErrorTitle }}</h3>
          <p class="text-sm text-txt-secondary mb-5 leading-relaxed">{{ serviceErrorMessage }}</p>
          <div class="flex gap-3 justify-center">
            <button @click="closeServiceError" class="px-4 py-2 text-sm text-txt-muted hover:text-txt-primary transition-colors">
              Dismiss
            </button>
            <button v-if="serviceErrorRetryFn" @click="retryFromServiceError" class="px-4 py-2 text-sm font-medium bg-indigo-500 text-white rounded-lg hover:bg-indigo-400 transition-colors">
              Try Again
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
