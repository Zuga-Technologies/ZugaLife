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
  <div class="narrative-card animate-fade-in">
    <!-- Accent glow line -->
    <div class="narrative-glow" />

    <div class="p-5 sm:p-6">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center">
            <BookOpen :size="16" class="text-purple-400" />
          </div>
          <div>
            <h3 class="text-sm font-bold text-txt-primary leading-none">Your Week in Review</h3>
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
      <div v-if="loading" class="flex items-center gap-3 py-6 justify-center">
        <Sparkles :size="16" class="text-purple-400 animate-pulse" />
        <span class="text-sm text-txt-muted">Synthesizing your week...</span>
      </div>

      <!-- Error -->
      <p v-else-if="error" class="text-xs text-txt-muted py-4 text-center">{{ error }}</p>

      <!-- Narrative -->
      <template v-else-if="data?.narrative">
        <div class="text-[13px] text-txt-secondary leading-[1.7] whitespace-pre-line">
          {{ data.narrative }}
        </div>

        <!-- Highlights -->
        <div v-if="data.highlights.length > 0" class="flex flex-wrap gap-2 mt-4 pt-4 border-t border-bdr/30">
          <span
            v-for="(h, i) in data.highlights"
            :key="i"
            class="text-[10px] px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/15 backdrop-blur-sm"
          >{{ h }}</span>
        </div>
      </template>

      <!-- No data yet -->
      <div v-else class="text-center py-6">
        <Sparkles :size="20" class="text-txt-muted/30 mx-auto mb-2" />
        <p class="text-xs text-txt-muted">Keep tracking throughout the week</p>
        <p class="text-[10px] text-txt-muted/60 mt-1">Your personalized narrative will appear here</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.narrative-card {
  position: relative;
  border-radius: 1rem;
  background: rgba(15, 15, 28, 0.7);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(139, 92, 246, 0.12);
  overflow: hidden;
}

.narrative-glow {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent 0%, rgba(139, 92, 246, 0.6) 30%, rgba(168, 85, 247, 0.8) 50%, rgba(139, 92, 246, 0.6) 70%, transparent 100%);
}

.narrative-card:hover {
  border-color: rgba(139, 92, 246, 0.2);
}
</style>
