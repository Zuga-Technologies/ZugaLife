<script setup lang="ts">
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

const categoryConfig: Record<string, { icon: any; color: string; glow: string; accentRgb: string }> = {
  neuroscience: { icon: Brain, color: 'text-accent-alt', glow: 'rgb(var(--accent-alt) / 0.15)', accentRgb: 'var(--accent-alt)' },
  psychology: { icon: Lightbulb, color: 'text-accent', glow: 'rgb(var(--accent) / 0.15)', accentRgb: 'var(--accent)' },
  research: { icon: BookOpen, color: 'text-info', glow: 'rgb(var(--color-info) / 0.15)', accentRgb: 'var(--color-info)' },
  pattern: { icon: BarChart3, color: 'text-success', glow: 'rgb(var(--color-success) / 0.15)', accentRgb: 'var(--color-success)' },
}

const config = categoryConfig[props.category] || categoryConfig.psychology
</script>

<template>
  <div
    class="insight-card animate-fade-in"
    :style="{ '--accent-rgb': config.accentRgb, '--accent-glow': config.glow }"
  >
    <!-- Side accent bar -->
    <div class="insight-accent" />

    <button
      @click="emit('dismiss', insightKey)"
      class="absolute top-3 right-3 w-6 h-6 rounded-md flex items-center justify-center text-txt-muted/30 hover:text-txt-muted hover:bg-surface-3/50 transition-all z-10"
      aria-label="Dismiss"
    >
      <X :size="12" />
    </button>

    <div class="flex items-start gap-3 p-4 sm:p-5">
      <!-- Category icon -->
      <div
        class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
        :style="{ background: config.glow }"
      >
        <component :is="config.icon" :size="18" :class="config.color" />
      </div>

      <div class="flex-1 min-w-0 pr-4">
        <p class="text-[9px] font-bold uppercase tracking-[0.15em] mb-1 opacity-70" :class="config.color">
          {{ category }}
        </p>
        <p class="text-sm font-semibold text-txt-primary mb-1.5 leading-snug">{{ title }}</p>
        <p class="text-xs text-txt-secondary/80 leading-relaxed">{{ content }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.insight-card {
  position: relative;
  border-radius: 0.75rem;
  background: rgba(17, 17, 17, 0.75);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(38, 38, 38, 1);
  overflow: hidden;
  transition: border-color 0.2s;
}

.insight-card:hover {
  border-color: rgba(var(--accent-rgb), 0.25);
}

.insight-accent {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(
    180deg,
    rgba(var(--accent-rgb), 0.8) 0%,
    rgba(var(--accent-rgb), 0.3) 100%
  );
}

.animate-fade-in {
  animation: insight-in 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

@keyframes insight-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
