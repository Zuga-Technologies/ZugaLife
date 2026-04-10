<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { BookOpen, RefreshCw, Sparkles } from 'lucide-vue-next'

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
  <div class="glass-card p-5 sm:p-6 animate-fade-in h-full flex flex-col">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center">
          <BookOpen :size="16" class="text-purple-400" />
        </div>
        <div>
          <h3 class="text-sm font-semibold text-txt-primary leading-none">Your Week in Review</h3>
          <p class="text-[10px] text-txt-muted mt-0.5">AI-powered wellness summary</p>
        </div>
      </div>
      <button
        v-if="data?.narrative && !loading"
        @click="fetchNarrative"
        class="w-7 h-7 rounded-lg bg-surface-3/50 flex items-center justify-center text-txt-muted hover:text-accent hover:bg-surface-3 transition-all"
        title="Regenerate"
      >
        <RefreshCw :size="12" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center gap-3 justify-center">
      <Sparkles :size="16" class="text-purple-400 animate-pulse" />
      <span class="text-sm text-txt-muted">Synthesizing your week...</span>
    </div>

    <!-- Error -->
    <p v-else-if="error" class="flex-1 text-xs text-txt-muted py-4 text-center">{{ error }}</p>

    <!-- Narrative -->
    <template v-else-if="data?.narrative">
      <div class="text-[13px] text-txt-secondary leading-[1.7] whitespace-pre-line flex-1">
        {{ data.narrative }}
      </div>

      <!-- Highlights -->
      <div v-if="data.highlights.length > 0" class="flex flex-wrap gap-2 mt-4 pt-4 border-t border-bdr/50">
        <span
          v-for="(h, i) in data.highlights"
          :key="i"
          class="text-[10px] px-2.5 py-1 rounded-full bg-accent/10 text-accent border border-accent/15"
        >{{ h }}</span>
      </div>
    </template>

    <!-- No data yet -->
    <div v-else class="flex-1 flex flex-col items-center justify-center text-center py-6">
      <Sparkles :size="20" class="text-txt-muted/30 mb-2" />
      <p class="text-xs text-txt-muted">Keep tracking throughout the week</p>
      <p class="text-[10px] text-txt-muted/60 mt-1">Your personalized narrative will appear here</p>
    </div>
  </div>
</template>
