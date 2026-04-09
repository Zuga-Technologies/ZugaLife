<script setup lang="ts">
/**
 * WoopGoalWizard — 5-step WOOP goal creation flow.
 *
 * Psychology: Gabriele Oettingen's WOOP (Wish-Outcome-Obstacle-Plan) framework
 * doubles goal follow-through in RCTs vs. standard goal-setting.
 *
 * Steps:
 * 1. Identity — "Who do you want to become?"
 * 2. Outcome — Title + description + deadline
 * 3. Visualize — "Imagine achieving this"
 * 4. Obstacle — "What could stop you?"
 * 5. Plan — "When [obstacle], I will..."
 */
import { ref, computed } from 'vue'
import { ChevronLeft, ChevronRight, Target, Sparkles, Shield, Zap, User } from 'lucide-vue-next'

const emit = defineEmits<{
  (e: 'create', goal: {
    title: string
    description: string | null
    deadline: string | null
    identity_statement: string | null
    obstacle: string | null
    implementation_plan: string | null
    approach_reframe: string | null
  }): void
  (e: 'cancel'): void
}>()

const step = ref(1)
const totalSteps = 5

// Step 1: Identity
const identity = ref('')
const identitySuggestions = [
  'Someone who prioritizes their mental health',
  'A person who follows through on commitments',
  'Someone who takes care of their body',
  'A mindful, present person',
  'Someone who never stops growing',
]

// Step 2: Outcome
const title = ref('')
const description = ref('')
const deadline = ref('')

// Step 3: Visualize (stored in description or separate)
const visualization = ref('')

// Step 4: Obstacle
const obstacle = ref('')
const obstacleSuggestions = [
  'I lose motivation after the first week',
  'I get too busy and forget',
  'I feel overwhelmed and give up',
  'I talk myself out of it',
  'I don\'t see results fast enough',
]

// Step 5: Plan
const plan = ref('')

const canProceed = computed(() => {
  switch (step.value) {
    case 1: return identity.value.trim().length > 0
    case 2: return title.value.trim().length > 0
    case 3: return true // visualization is optional
    case 4: return obstacle.value.trim().length > 0
    case 5: return plan.value.trim().length > 0
    default: return false
  }
})

const stepLabels = ['Identity', 'Outcome', 'Visualize', 'Obstacle', 'Plan']
const stepIcons = [User, Target, Sparkles, Shield, Zap]

function next() {
  if (step.value < totalSteps && canProceed.value) {
    step.value++
  }
}

function prev() {
  if (step.value > 1) step.value--
}

function submit() {
  const fullDescription = visualization.value.trim()
    ? `${description.value.trim()}\n\n---\nVisualization: ${visualization.value.trim()}`
    : description.value.trim() || null

  emit('create', {
    title: title.value.trim(),
    description: fullDescription,
    deadline: deadline.value || null,
    identity_statement: identity.value.trim() || null,
    obstacle: obstacle.value.trim() || null,
    implementation_plan: plan.value.trim() || null,
    approach_reframe: null,
  })
}
</script>

<template>
  <div class="woop-wizard">
    <!-- Progress bar -->
    <div class="flex items-center gap-1 mb-6">
      <div
        v-for="i in totalSteps"
        :key="i"
        class="flex-1 h-1.5 rounded-full transition-all duration-300"
        :class="i <= step ? 'bg-accent' : 'bg-surface-3'"
      />
    </div>

    <!-- Step indicator -->
    <div class="flex items-center gap-2 mb-4">
      <component :is="stepIcons[step - 1]" :size="16" class="text-accent" />
      <span class="text-[11px] font-bold uppercase tracking-wider text-accent">
        Step {{ step }}/{{ totalSteps }} &mdash; {{ stepLabels[step - 1] }}
      </span>
    </div>

    <!-- Step 1: Identity -->
    <div v-if="step === 1" class="space-y-4 animate-fade-in">
      <h3 class="text-lg font-bold text-txt-primary">Who do you want to become?</h3>
      <p class="text-sm text-txt-muted">Goals rooted in identity last longer than goals tied to outcomes.</p>
      <div class="flex flex-wrap gap-1.5 mb-2">
        <button
          v-for="s in identitySuggestions"
          :key="s"
          @click="identity = s"
          class="px-2.5 py-1.5 text-xs rounded-lg border transition-colors"
          :class="identity === s
            ? 'bg-accent/20 border-accent text-accent'
            : 'border-bdr text-txt-muted hover:border-accent/50'"
        >{{ s }}</button>
      </div>
      <input
        v-model="identity"
        type="text"
        placeholder="Or describe in your own words..."
        maxlength="500"
        class="input-field text-sm w-full"
      />
    </div>

    <!-- Step 2: Outcome -->
    <div v-if="step === 2" class="space-y-4 animate-fade-in">
      <h3 class="text-lg font-bold text-txt-primary">What's your goal?</h3>
      <p class="text-sm text-txt-muted">Be specific. "Run a 5K" beats "get fit."</p>
      <input
        v-model="title"
        type="text"
        placeholder="Goal title"
        maxlength="200"
        class="input-field text-sm w-full"
      />
      <textarea
        v-model="description"
        placeholder="Describe what success looks like (optional)"
        maxlength="2000"
        rows="3"
        class="input-field text-sm w-full resize-none"
      />
      <div>
        <label class="text-[11px] text-txt-muted mb-1 block">Deadline (optional)</label>
        <input
          v-model="deadline"
          type="date"
          class="input-field text-sm"
        />
      </div>
    </div>

    <!-- Step 3: Visualize -->
    <div v-if="step === 3" class="space-y-4 animate-fade-in">
      <h3 class="text-lg font-bold text-txt-primary">Imagine you've achieved this</h3>
      <p class="text-sm text-txt-muted">Close your eyes for a moment. What does that day look like? How do you feel?</p>
      <textarea
        v-model="visualization"
        placeholder="Describe the moment you've achieved your goal..."
        maxlength="2000"
        rows="4"
        class="input-field text-sm w-full resize-none"
      />
      <p class="text-[11px] text-txt-muted">This step activates motivational circuits through mental contrasting. You can skip it, but research shows it helps.</p>
    </div>

    <!-- Step 4: Obstacle -->
    <div v-if="step === 4" class="space-y-4 animate-fade-in">
      <h3 class="text-lg font-bold text-txt-primary">What's most likely to stop you?</h3>
      <p class="text-sm text-txt-muted">Not external excuses &mdash; what internal resistance will you face?</p>
      <div class="flex flex-wrap gap-1.5 mb-2">
        <button
          v-for="s in obstacleSuggestions"
          :key="s"
          @click="obstacle = s"
          class="px-2.5 py-1.5 text-xs rounded-lg border transition-colors"
          :class="obstacle === s
            ? 'bg-red-500/20 border-red-500/50 text-red-300'
            : 'border-bdr text-txt-muted hover:border-red-500/30'"
        >{{ s }}</button>
      </div>
      <input
        v-model="obstacle"
        type="text"
        placeholder="Or describe your biggest obstacle..."
        maxlength="500"
        class="input-field text-sm w-full"
      />
    </div>

    <!-- Step 5: Plan -->
    <div v-if="step === 5" class="space-y-4 animate-fade-in">
      <h3 class="text-lg font-bold text-txt-primary">When that happens, I will...</h3>
      <p class="text-sm text-txt-muted">
        This if-then plan fires automatically when your obstacle appears &mdash; no willpower needed.
      </p>
      <div class="p-3 rounded-lg bg-red-500/10 border border-red-500/20 mb-3">
        <p class="text-xs text-red-300"><strong>When:</strong> {{ obstacle }}</p>
      </div>
      <textarea
        v-model="plan"
        :placeholder="`When '${obstacle.slice(0, 40)}...' happens, I will...`"
        maxlength="2000"
        rows="3"
        class="input-field text-sm w-full resize-none"
      />
    </div>

    <!-- Navigation -->
    <div class="flex items-center gap-3 mt-6">
      <button
        v-if="step > 1"
        @click="prev"
        class="flex items-center gap-1 text-sm text-txt-muted hover:text-txt-secondary transition-colors"
      >
        <ChevronLeft :size="16" /> Back
      </button>
      <button
        v-else
        @click="$emit('cancel')"
        class="text-sm text-txt-muted hover:text-txt-secondary transition-colors"
      >Cancel</button>

      <div class="flex-1" />

      <button
        v-if="step < totalSteps"
        @click="next"
        :disabled="!canProceed"
        class="btn-primary text-sm flex items-center gap-1"
      >
        Next <ChevronRight :size="16" />
      </button>
      <button
        v-else
        @click="submit"
        :disabled="!canProceed"
        class="btn-primary text-sm flex items-center gap-1"
      >
        <Target :size="16" /> Create Goal
      </button>
    </div>
  </div>
</template>

<style scoped>
.woop-wizard {
  padding: 1rem;
}

.animate-fade-in {
  animation: fade-in 0.3s ease;
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
