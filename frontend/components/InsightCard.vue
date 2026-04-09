<script setup lang="ts">
/**
 * InsightCard — Contextual psychological micro-learning card.
 *
 * Displayed at psychologically optimal moments — after meditation streaks,
 * mood pattern detection, goal milestones. Deepstash-inspired: bite-sized
 * research insights that stick because they arrive at the right time.
 */
import { X, Brain, Lightbulb, BarChart3, BookOpen } from 'lucide-vue-next'

const props = defineProps<{
  insightKey: string
  title: string
  content: string
  category: string
}>()

const emit = defineEmits<{
  (e: 'dismiss', key: string): void
}>()

const categoryConfig: Record<string, { icon: any; color: string; bg: string; border: string }> = {
  neuroscience: { icon: Brain, color: 'text-purple-400', bg: 'bg-purple-500/8', border: 'border-purple-500/20' },
  psychology: { icon: Lightbulb, color: 'text-amber-400', bg: 'bg-amber-500/8', border: 'border-amber-500/20' },
  research: { icon: BookOpen, color: 'text-cyan-400', bg: 'bg-cyan-500/8', border: 'border-cyan-500/20' },
  pattern: { icon: BarChart3, color: 'text-emerald-400', bg: 'bg-emerald-500/8', border: 'border-emerald-500/20' },
}

const config = categoryConfig[props.category] || categoryConfig.psychology
</script>

<template>
  <div
    class="p-4 rounded-xl border animate-fade-in relative"
    :class="[config.bg, config.border]"
  >
    <button
      @click="emit('dismiss', insightKey)"
      class="absolute top-2 right-2 p-1 text-txt-muted/40 hover:text-txt-muted transition-colors"
      aria-label="Dismiss"
    >
      <X :size="14" />
    </button>

    <div class="flex items-start gap-3">
      <component :is="config.icon" :size="18" :class="config.color" class="flex-shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0 pr-4">
        <p class="text-[10px] font-bold uppercase tracking-wider mb-0.5" :class="config.color">
          {{ category }}
        </p>
        <p class="text-sm font-semibold text-txt-primary mb-1.5">{{ title }}</p>
        <p class="text-xs text-txt-secondary leading-relaxed">{{ content }}</p>
      </div>
    </div>
  </div>
</template>
