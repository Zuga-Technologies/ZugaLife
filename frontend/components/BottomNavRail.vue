<script setup lang="ts">
import { Home, BookOpen, Activity, Brain, MessageCircleHeart } from 'lucide-vue-next'

defineProps<{ activeTab: string }>()
const emit = defineEmits<{ (e: 'navigate', tab: string): void }>()

const items = [
  { id: 'dashboard', icon: Home, label: 'Home' },
  { id: 'journal', icon: BookOpen, label: 'Journal' },
  { id: 'habits', icon: Activity, label: 'Habits' },
  { id: 'meditate', icon: Brain, label: 'Meditate' },
  { id: 'therapist', icon: MessageCircleHeart, label: 'Companion' },
] as const
</script>

<template>
  <nav
    class="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-surface-0/95 backdrop-blur-lg border-t border-bdr"
    aria-label="Primary navigation"
  >
    <div
      class="flex items-stretch justify-around h-16"
      style="padding-bottom: env(safe-area-inset-bottom)"
    >
      <button
        v-for="item in items"
        :key="item.id"
        @click="emit('navigate', item.id)"
        class="flex-1 flex flex-col items-center justify-center gap-1 transition-colors active:scale-95"
        :class="activeTab === item.id ? 'text-accent' : 'text-txt-muted hover:text-txt-secondary'"
        :aria-current="activeTab === item.id ? 'page' : undefined"
        :aria-label="item.label"
      >
        <component :is="item.icon" :size="22" :stroke-width="activeTab === item.id ? 2.4 : 1.8" />
        <span class="text-[10px] font-semibold tracking-wide">{{ item.label }}</span>
      </button>
    </div>
  </nav>
</template>
