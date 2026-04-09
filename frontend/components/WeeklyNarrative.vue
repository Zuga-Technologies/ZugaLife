<script setup lang="ts">
/**
 * WeeklyNarrative — AI-generated weekly wellness summary.
 *
 * Psychology: The #1 gap in mood tracking research is lack of interpretation.
 * Users want patterns and narrative, not raw data. This transforms a week of
 * mood/habit/goal data into a cohesive story that reinforces identity and
 * surfaces actionable insights.
 */
import { ref, onMounted } from 'vue'
import { BookOpen, RefreshCw, Sparkles } from 'lucide-vue-next'

// API helper injected from parent (or use direct fetch)
const props = defineProps<{
  api: {
    get: <T>(url: string) => Promise<T>
  }
}>()

interface NarrativeResponse {
  narrative: string | null
  highlights: string[]
  generated_at: string | null
  cached?: boolean
  cost?: number
  error?: string
}

const data = ref<NarrativeResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function fetchNarrative() {
  loading.value = true
  error.value = null
  try {
    data.value = await props.api.get<NarrativeResponse>('/api/life/forecasting/narrative')
    if (data.value.error) {
      error.value = data.value.error
    }
  } catch (e: any) {
    error.value = e?.status === 402 ? 'Insufficient tokens' : 'Could not generate narrative'
  } finally {
    loading.value = false
  }
}

onMounted(fetchNarrative)
</script>

<template>
  <div class="glass-card p-5 animate-fade-in">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <BookOpen :size="16" class="text-purple-400" />
        <h3 class="text-sm font-bold text-txt-primary">Your Week in Review</h3>
      </div>
      <button
        v-if="data?.narrative && !loading"
        @click="fetchNarrative"
        class="text-[10px] text-txt-muted hover:text-accent transition-colors"
        title="Regenerate"
      >
        <RefreshCw :size="12" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 py-4">
      <Sparkles :size="14" class="text-purple-400 animate-pulse" />
      <span class="text-xs text-txt-muted">Synthesizing your week...</span>
    </div>

    <!-- Error -->
    <p v-else-if="error" class="text-xs text-txt-muted py-2">{{ error }}</p>

    <!-- Narrative -->
    <template v-else-if="data?.narrative">
      <div class="text-sm text-txt-secondary leading-relaxed whitespace-pre-line mb-3">
        {{ data.narrative }}
      </div>

      <!-- Highlights -->
      <div v-if="data.highlights.length > 0" class="flex flex-wrap gap-1.5">
        <span
          v-for="(h, i) in data.highlights"
          :key="i"
          class="text-[10px] px-2 py-1 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20"
        >{{ h }}</span>
      </div>
    </template>

    <!-- No data yet -->
    <p v-else class="text-xs text-txt-muted py-2">
      Keep tracking throughout the week — your narrative will appear here.
    </p>
  </div>
</template>
