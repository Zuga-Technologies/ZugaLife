<!--
  ZugaLife Studio Onboarding — 5-step flow modeled after best-in-class apps.

  1. "What matters most?" — goal anchoring (Headspace/Duolingo pattern)
  2. "How are you feeling?" — first mood log IS the onboarding (Daylio pattern)
  3. AI insight — personalized output based on answers (our moat)
  4. "Your toolkit" — contextual feature tour with recommended highlight
  5. Done — CTA to recommended feature

  Emits @complete when user finishes or skips.
-->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@core/api/client'
import {
  Heart, BookOpen, Target, Brain, Trophy, Smile,
  ArrowRight, ArrowLeft, X, Check, Sparkles,
  Wind, Moon, Lightbulb, TrendingUp,
} from 'lucide-vue-next'

const emit = defineEmits<{ complete: [recommendedTab?: string] }>()

const currentStep = ref(0)
const TOTAL_STEPS = 5

// ── Step 1: Goal selection ───────────────────────────────
const selectedGoal = ref<string | null>(null)

const goals = [
  { id: 'clarity', label: 'Mental clarity', icon: Lightbulb, desc: 'Think clearer, focus better' },
  { id: 'stress', label: 'Reduce stress', icon: Wind, desc: 'Find calm in the chaos' },
  { id: 'sleep', label: 'Better sleep', icon: Moon, desc: 'Wind down, rest deeper' },
  { id: 'habits', label: 'Build better habits', icon: TrendingUp, desc: 'Make good routines stick' },
  { id: 'understand', label: 'Understand myself', icon: Smile, desc: 'See patterns, grow from them' },
]

// ── Step 2: Mood selection ───────────────────────────────
const selectedMood = ref<string | null>(null)
const moodLogging = ref(false)
const moodLogged = ref(false)

const moodOptions = [
  { emoji: '😊', label: 'Happy' },
  { emoji: '😐', label: 'Neutral' },
  { emoji: '😰', label: 'Anxious' },
  { emoji: '😢', label: 'Sad' },
  { emoji: '😴', label: 'Tired' },
  { emoji: '💪', label: 'Motivated' },
]

async function logFirstMood() {
  if (!selectedMood.value || moodLogging.value) return
  moodLogging.value = true
  try {
    await api.post('/api/life/mood', {
      emoji: selectedMood.value,
      note: `First mood during onboarding — goal: ${selectedGoal.value || 'not set'}`,
    })
    moodLogged.value = true
    // Auto-advance after a brief pause
    setTimeout(() => next(), 800)
  } catch {
    // Still advance even if mood log fails (rate limit, etc)
    moodLogged.value = true
    setTimeout(() => next(), 800)
  } finally {
    moodLogging.value = false
  }
}

// ── Step 3: AI insight ───────────────────────────────────
const aiInsight = ref<string | null>(null)
const aiLoading = ref(false)

async function generateInsight() {
  if (aiLoading.value || aiInsight.value) return
  aiLoading.value = true

  const goalLabel = goals.find(g => g.id === selectedGoal.value)?.label || 'wellness'
  const moodLabel = moodOptions.find(m => m.emoji === selectedMood.value)?.label || 'neutral'

  // Simple AI call via gateway
  try {
    const res = await api.post<{ content: string }>('/api/ai/chat', {
      messages: [
        {
          role: 'system',
          content: 'You are a concise wellness advisor. Respond in exactly 2 sentences. Be warm but direct. No fluff.',
        },
        {
          role: 'user',
          content: `I just signed up for a wellness app. My main goal is "${goalLabel}" and right now I'm feeling "${moodLabel}". What's one small thing I should start with today, and why?`,
        },
      ],
      model: 'fast',
      max_tokens: 100,
    })
    aiInsight.value = res.content
  } catch {
    // Fallback insight if AI call fails (no tokens, etc)
    const fallbacks: Record<string, string> = {
      clarity: `You're feeling ${moodLabel.toLowerCase()} and want mental clarity. Start with a 2-minute journal entry — writing organizes thoughts faster than thinking about them.`,
      stress: `Feeling ${moodLabel.toLowerCase()} with stress on your mind. Try a short meditation — even 3 minutes of guided breathing resets your nervous system.`,
      sleep: `You're ${moodLabel.toLowerCase()} and want better sleep. Tonight, log your mood before bed — tracking what affects your rest is the first step to improving it.`,
      habits: `Feeling ${moodLabel.toLowerCase()} and ready to build habits. Pick one small thing — just one — and do it tomorrow. Consistency beats ambition every time.`,
      understand: `You're ${moodLabel.toLowerCase()} and want to understand yourself better. You just took the first step — logging how you feel. Keep it up and patterns will emerge.`,
    }
    aiInsight.value = fallbacks[selectedGoal.value || 'understand'] || fallbacks.understand
  } finally {
    aiLoading.value = false
  }
}

// ── Step 4: Feature recommendations ──────────────────────
const recommendedFeature = computed(() => {
  const map: Record<string, string> = {
    clarity: 'journal',
    stress: 'meditate',
    sleep: 'meditate',
    habits: 'habits',
    understand: 'mood',
  }
  return map[selectedGoal.value || 'understand'] || 'mood'
})

const features = computed(() => [
  {
    id: 'mood',
    icon: Smile,
    label: 'Mood Tracking',
    desc: 'Log how you feel. See patterns over time.',
    recommended: recommendedFeature.value === 'mood',
    tab: 'dashboard',
  },
  {
    id: 'journal',
    icon: BookOpen,
    label: 'Journal',
    desc: 'Write freely. AI reflects back insights.',
    recommended: recommendedFeature.value === 'journal',
    tab: 'journal',
  },
  {
    id: 'habits',
    icon: Target,
    label: 'Habits & Goals',
    desc: 'Build streaks. Track what matters.',
    recommended: recommendedFeature.value === 'habits',
    tab: 'habits',
  },
  {
    id: 'meditate',
    icon: Brain,
    label: 'Meditation',
    desc: 'AI-generated sessions tuned to you.',
    recommended: recommendedFeature.value === 'meditate',
    tab: 'meditate',
  },
  {
    id: 'challenges',
    icon: Trophy,
    label: 'Challenges',
    desc: 'Daily AI challenges. Earn XP. Level up.',
    recommended: false,
    tab: 'dashboard',
  },
])

// ── Navigation ───────────────────────────────────────────
function next() {
  if (currentStep.value < TOTAL_STEPS - 1) {
    currentStep.value++
    // Trigger AI insight generation when entering step 3
    if (currentStep.value === 2) {
      generateInsight()
    }
  }
}

function prev() {
  if (currentStep.value > 0) currentStep.value--
}

function skip() {
  emit('complete')
}

function finish(tab?: string) {
  emit('complete', tab || recommendedFeature.value)
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div class="relative w-full max-w-md mx-4 glass-card p-0 overflow-hidden animate-slide-up">

        <!-- Skip -->
        <button
          @click="skip"
          class="absolute top-4 right-4 z-10 p-1.5 rounded-lg text-txt-muted hover:text-txt-primary hover:bg-surface-3/50 transition-colors"
          title="Skip"
        >
          <X :size="18" />
        </button>

        <div class="px-8 pt-8 pb-6 min-h-[400px] flex flex-col">

          <!-- ─── Step 0: What matters most? ────────────── -->
          <template v-if="currentStep === 0">
            <div class="flex-1 flex flex-col">
              <div class="text-center mb-6">
                <div class="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center mx-auto mb-4">
                  <Heart :size="24" class="text-accent" />
                </div>
                <h2 class="text-xl font-bold text-txt-primary mb-2">
                  What matters most to you right now?
                </h2>
                <p class="text-sm text-txt-muted">This helps us personalize your experience.</p>
              </div>

              <div class="space-y-2 flex-1">
                <button
                  v-for="goal in goals"
                  :key="goal.id"
                  @click="selectedGoal = goal.id"
                  class="w-full flex items-center gap-3 p-3.5 rounded-xl border transition-all duration-200 text-left"
                  :class="selectedGoal === goal.id
                    ? 'bg-accent/10 border-accent/40 ring-1 ring-accent/20'
                    : 'bg-surface-2/50 border-bdr/50 hover:border-bdr-hover hover:bg-surface-2'"
                >
                  <div
                    class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors"
                    :class="selectedGoal === goal.id ? 'bg-accent/20' : 'bg-surface-3'"
                  >
                    <component :is="goal.icon" :size="18" :class="selectedGoal === goal.id ? 'text-accent' : 'text-txt-muted'" />
                  </div>
                  <div>
                    <p class="text-sm font-medium" :class="selectedGoal === goal.id ? 'text-accent' : 'text-txt-primary'">
                      {{ goal.label }}
                    </p>
                    <p class="text-xs text-txt-muted">{{ goal.desc }}</p>
                  </div>
                </button>
              </div>
            </div>
          </template>

          <!-- ─── Step 1: How are you feeling? ────────────── -->
          <template v-else-if="currentStep === 1">
            <div class="flex-1 flex flex-col items-center justify-center text-center">
              <h2 class="text-xl font-bold text-txt-primary mb-2">
                How are you feeling right now?
              </h2>
              <p class="text-sm text-txt-muted mb-8">Tap one — this logs your first mood.</p>

              <div class="grid grid-cols-3 gap-3 w-full max-w-xs mb-6">
                <button
                  v-for="mood in moodOptions"
                  :key="mood.emoji"
                  @click="selectedMood = mood.emoji; logFirstMood()"
                  :disabled="moodLogging || moodLogged"
                  class="flex flex-col items-center gap-1.5 p-4 rounded-xl border transition-all duration-200"
                  :class="selectedMood === mood.emoji
                    ? 'bg-accent/15 border-accent/40 ring-1 ring-accent/20 scale-105'
                    : moodLogged
                      ? 'bg-surface-2/30 border-bdr/30 opacity-40'
                      : 'bg-surface-2/50 border-bdr/50 hover:border-bdr-hover hover:bg-surface-2 hover:scale-105'"
                >
                  <span class="text-2xl">{{ mood.emoji }}</span>
                  <span class="text-xs" :class="selectedMood === mood.emoji ? 'text-accent font-medium' : 'text-txt-muted'">
                    {{ mood.label }}
                  </span>
                </button>
              </div>

              <!-- Success feedback -->
              <transition name="fade">
                <div v-if="moodLogged" class="flex items-center gap-2 text-emerald-400 text-sm font-medium">
                  <Check :size="16" />
                  First mood logged!
                </div>
              </transition>
            </div>
          </template>

          <!-- ─── Step 2: AI Insight ──────────────────────── -->
          <template v-else-if="currentStep === 2">
            <div class="flex-1 flex flex-col items-center justify-center text-center">
              <div class="w-12 h-12 rounded-2xl bg-purple-500/10 flex items-center justify-center mb-5">
                <Sparkles :size="24" class="text-purple-400" />
              </div>
              <h2 class="text-xl font-bold text-txt-primary mb-2">
                Here's what we think
              </h2>
              <p class="text-xs text-txt-muted mb-6">Based on your goal and how you're feeling</p>

              <div class="glass-card p-5 text-left max-w-sm">
                <template v-if="aiLoading">
                  <div class="flex items-center gap-3">
                    <div class="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                    <span class="text-sm text-txt-secondary">Thinking about you...</span>
                  </div>
                </template>
                <template v-else-if="aiInsight">
                  <p class="text-sm text-txt-primary leading-relaxed">{{ aiInsight }}</p>
                </template>
              </div>
            </div>
          </template>

          <!-- ─── Step 3: Your toolkit ────────────────────── -->
          <template v-else-if="currentStep === 3">
            <div class="flex-1 flex flex-col">
              <h2 class="text-lg font-bold text-txt-primary mb-1 text-center">Your toolkit</h2>
              <p class="text-xs text-txt-muted text-center mb-4">We recommend starting with the highlighted one.</p>

              <div class="space-y-2 flex-1">
                <div
                  v-for="feature in features"
                  :key="feature.id"
                  class="flex items-center gap-3 p-3 rounded-xl border transition-colors"
                  :class="feature.recommended
                    ? 'bg-accent/10 border-accent/30'
                    : 'bg-surface-2/50 border-bdr/50'"
                >
                  <div
                    class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    :class="feature.recommended ? 'bg-accent/20' : 'bg-surface-3'"
                  >
                    <component :is="feature.icon" :size="16" :class="feature.recommended ? 'text-accent' : 'text-txt-muted'" />
                  </div>
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <p class="text-sm font-medium" :class="feature.recommended ? 'text-accent' : 'text-txt-primary'">
                        {{ feature.label }}
                      </p>
                      <span v-if="feature.recommended" class="text-[10px] font-semibold text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                        RECOMMENDED
                      </span>
                    </div>
                    <p class="text-xs text-txt-muted">{{ feature.desc }}</p>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- ─── Step 4: Done ────────────────────────────── -->
          <template v-else-if="currentStep === 4">
            <div class="flex-1 flex flex-col items-center justify-center text-center">
              <div class="w-14 h-14 rounded-2xl bg-emerald-500/10 flex items-center justify-center mb-5">
                <Check :size="28" class="text-emerald-400" />
              </div>
              <h2 class="text-xl font-bold text-txt-primary mb-3">
                You're all set
              </h2>
              <p class="text-sm text-txt-secondary max-w-xs leading-relaxed mb-6">
                Your first mood is logged and your toolkit is ready.
                Start with what matters most to you.
              </p>
              <button
                @click="finish()"
                class="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-accent text-black font-semibold text-sm hover:bg-accent/90 transition-colors"
              >
                Let's go
                <ArrowRight :size="14" />
              </button>
            </div>
          </template>
        </div>

        <!-- Footer -->
        <div class="px-8 pb-6 flex items-center justify-between">
          <button
            v-if="currentStep > 0 && currentStep < TOTAL_STEPS - 1"
            @click="prev"
            class="flex items-center gap-1 text-sm text-txt-muted hover:text-txt-primary transition-colors"
          >
            <ArrowLeft :size="14" /> Back
          </button>
          <div v-else />

          <!-- Progress dots -->
          <div class="flex items-center gap-1.5">
            <div
              v-for="i in TOTAL_STEPS"
              :key="i"
              class="w-2 h-2 rounded-full transition-colors duration-300"
              :class="i - 1 === currentStep ? 'bg-accent' : i - 1 < currentStep ? 'bg-accent/40' : 'bg-surface-3'"
            />
          </div>

          <button
            v-if="currentStep === 0"
            @click="next"
            :disabled="!selectedGoal"
            class="flex items-center gap-1 text-sm font-medium transition-colors"
            :class="selectedGoal ? 'text-accent hover:text-accent/80' : 'text-txt-muted cursor-not-allowed'"
          >
            Next <ArrowRight :size="14" />
          </button>
          <button
            v-else-if="currentStep > 1 && currentStep < TOTAL_STEPS - 1"
            @click="next"
            class="flex items-center gap-1 text-sm font-medium text-accent hover:text-accent/80 transition-colors"
          >
            Next <ArrowRight :size="14" />
          </button>
          <div v-else />
        </div>
      </div>
    </div>
  </Teleport>
</template>
