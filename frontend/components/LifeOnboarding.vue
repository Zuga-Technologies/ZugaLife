<!--
  ZugaLife Studio Onboarding — shown on first visit.

  Template for future studio onboardings:
  1. Copy this file to your studio's frontend/components/
  2. Customize the steps (icons, labels, descriptions)
  3. Emit @complete when the user finishes or skips
  4. Parent component toggles visibility based on studio settings
-->
<script setup lang="ts">
import { ref } from 'vue'
import {
  Heart, BookOpen, Target, Brain, Trophy,
  ArrowRight, ArrowLeft, X, Check, Smile,
} from 'lucide-vue-next'

const emit = defineEmits<{ complete: [] }>()

const currentStep = ref(0)
const TOTAL_STEPS = 3

function next() {
  if (currentStep.value < TOTAL_STEPS - 1) {
    currentStep.value++
  }
}

function prev() {
  if (currentStep.value > 0) currentStep.value--
}

function skip() {
  emit('complete')
}

function finish() {
  emit('complete')
}

const features = [
  { icon: Smile, label: 'Mood Tracking', desc: 'Log your mood daily and discover emotional patterns over time.' },
  { icon: BookOpen, label: 'Journal', desc: 'Write freely. AI reflects back insights you might have missed.' },
  { icon: Target, label: 'Habits & Goals', desc: 'Set habits, track streaks, and link goals to milestones.' },
  { icon: Brain, label: 'Meditation', desc: 'AI-generated sessions based on your mood and preferences.' },
  { icon: Trophy, label: 'Gamification', desc: 'Earn XP, unlock badges, and complete daily challenges.' },
]
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div class="relative w-full max-w-md mx-4 glass-card p-0 overflow-hidden animate-slide-up">

        <!-- Skip -->
        <button
          @click="skip"
          class="absolute top-4 right-4 z-10 p-1.5 rounded-lg text-txt-muted hover:text-txt-primary hover:bg-surface-3/50 transition-colors"
          title="Skip tutorial"
        >
          <X :size="18" />
        </button>

        <div class="px-8 pt-8 pb-6 min-h-[340px] flex flex-col">

          <!-- ─── Step 0: Welcome ──────────────────────── -->
          <template v-if="currentStep === 0">
            <div class="flex-1 flex flex-col items-center justify-center text-center">
              <div class="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center mb-5">
                <Heart :size="28" class="text-accent" />
              </div>
              <h2 class="text-xl font-bold text-txt-primary mb-3">
                Welcome to ZugaLife
              </h2>
              <p class="text-sm text-txt-secondary max-w-xs leading-relaxed">
                Your personal wellness companion. Track your mood, journal your thoughts,
                build habits, and grow &mdash; with AI that actually understands you.
              </p>
            </div>
          </template>

          <!-- ─── Step 1: Feature Tour ─────────────────── -->
          <template v-else-if="currentStep === 1">
            <div class="flex-1 flex flex-col">
              <h2 class="text-lg font-bold text-txt-primary mb-4 text-center">
                What you can do
              </h2>
              <div class="space-y-2.5 flex-1">
                <div
                  v-for="feature in features"
                  :key="feature.label"
                  class="flex items-start gap-3 p-3 rounded-xl bg-surface-2/50 border border-bdr/50"
                >
                  <div class="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
                    <component :is="feature.icon" :size="16" class="text-accent" />
                  </div>
                  <div>
                    <p class="text-sm font-medium text-txt-primary">{{ feature.label }}</p>
                    <p class="text-xs text-txt-muted leading-relaxed">{{ feature.desc }}</p>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- ─── Step 2: Get Started ──────────────────── -->
          <template v-else-if="currentStep === 2">
            <div class="flex-1 flex flex-col items-center justify-center text-center">
              <div class="w-14 h-14 rounded-2xl bg-emerald-500/10 flex items-center justify-center mb-5">
                <Check :size="28" class="text-emerald-400" />
              </div>
              <h2 class="text-xl font-bold text-txt-primary mb-3">
                Ready to start
              </h2>
              <p class="text-sm text-txt-secondary max-w-xs leading-relaxed mb-6">
                Try logging your first mood &mdash; it only takes a second.
                Everything you track builds a picture that helps ZugaLife
                help you.
              </p>
              <button
                @click="finish"
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
            v-if="currentStep > 0"
            @click="prev"
            class="flex items-center gap-1 text-sm text-txt-muted hover:text-txt-primary transition-colors"
          >
            <ArrowLeft :size="14" /> Back
          </button>
          <div v-else />

          <div class="flex items-center gap-1.5">
            <div
              v-for="i in TOTAL_STEPS"
              :key="i"
              class="w-2 h-2 rounded-full transition-colors duration-300"
              :class="i - 1 === currentStep ? 'bg-accent' : 'bg-surface-3'"
            />
          </div>

          <button
            v-if="currentStep < TOTAL_STEPS - 1"
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
