<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { X, Download, Share2 } from 'lucide-vue-next'

interface CardData {
  displayName: string
  level: number
  levelName: string
  totalXp: number
  currentStreak: number
  longestStreak: number
  badgeCount: number
  topBadges: Array<{ emoji: string; title: string }>
  moodCount: number
  topMood: { emoji: string; label: string } | null
  journalCount: number
  meditationCount: number
  meditationMinutes: number
  habitCompletionRate: number
  goalsCompleted: number
  prestigeLevel: number
  date: string
}

const props = defineProps<{
  data: CardData
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const cardRef = ref<HTMLElement | null>(null)
const capturing = ref(false)

const streakLabel = computed(() => {
  const d = props.data.currentStreak
  if (d === 0) return 'Start your streak today'
  if (d === 1) return '1 day streak'
  return `${d} day streak`
})

const formattedDate = computed(() => {
  const d = new Date(props.data.date)
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
})

async function downloadCard() {
  if (!cardRef.value || capturing.value) return
  capturing.value = true

  try {
    // Use html2canvas-like approach via Canvas API
    const card = cardRef.value
    const canvas = document.createElement('canvas')
    const scale = 2 // retina
    canvas.width = 600 * scale
    canvas.height = 800 * scale
    const ctx = canvas.getContext('2d')!
    ctx.scale(scale, scale)

    // Background
    const gradient = ctx.createLinearGradient(0, 0, 600, 800)
    gradient.addColorStop(0, '#0f0f23')
    gradient.addColorStop(0.5, '#1a1a3e')
    gradient.addColorStop(1, '#0a0a1a')
    ctx.fillStyle = gradient
    ctx.roundRect(0, 0, 600, 800, 24)
    ctx.fill()

    // Accent line at top
    ctx.fillStyle = '#6366f1'
    ctx.roundRect(0, 0, 600, 6, [24, 24, 0, 0])
    ctx.fill()

    // Helper: draw text
    const drawText = (text: string, x: number, y: number, opts: { color?: string; size?: number; weight?: string; align?: CanvasTextAlign } = {}) => {
      ctx.fillStyle = opts.color || '#e2e8f0'
      ctx.font = `${opts.weight || 'normal'} ${opts.size || 14}px Inter, system-ui, sans-serif`
      ctx.textAlign = opts.align || 'left'
      ctx.fillText(text, x, y)
    }

    // Header
    drawText('ZugaLife', 40, 50, { color: '#6366f1', size: 16, weight: 'bold' })
    drawText(formattedDate.value, 560, 50, { color: '#64748b', size: 13, align: 'right' })

    // Name + Level
    const name = props.data.displayName || 'Wellness Journey'
    drawText(name, 40, 100, { size: 28, weight: 'bold' })
    drawText(`Level ${props.data.level} — ${props.data.levelName}`, 40, 130, { color: '#6366f1', size: 16, weight: '600' })
    if (props.data.prestigeLevel > 0) {
      drawText(`Prestige ${props.data.prestigeLevel}`, 40, 155, { color: '#fbbf24', size: 13, weight: '600' })
    }

    // XP Bar
    const barY = props.data.prestigeLevel > 0 ? 175 : 160
    ctx.fillStyle = '#1e1e3f'
    ctx.roundRect(40, barY, 520, 12, 6)
    ctx.fill()
    const xpPct = Math.min(1, props.data.totalXp > 0 ? 0.65 : 0) // approximate
    ctx.fillStyle = '#6366f1'
    ctx.roundRect(40, barY, 520 * xpPct, 12, 6)
    ctx.fill()
    drawText(`${props.data.totalXp.toLocaleString()} XP`, 560, barY + 30, { color: '#94a3b8', size: 12, align: 'right' })

    // Stats grid
    const statsY = barY + 60
    const stats = [
      { emoji: '🔥', label: 'Streak', value: `${props.data.currentStreak} days` },
      { emoji: '📝', label: 'Journal', value: `${props.data.journalCount} entries` },
      { emoji: '🧘', label: 'Meditation', value: `${props.data.meditationMinutes} min` },
      { emoji: '✅', label: 'Habits', value: `${Math.round(props.data.habitCompletionRate * 100)}%` },
    ]

    for (let i = 0; i < stats.length; i++) {
      const col = i % 2
      const row = Math.floor(i / 2)
      const x = 40 + col * 270
      const y = statsY + row * 100

      // Stat card background
      ctx.fillStyle = '#ffffff08'
      ctx.roundRect(x, y, 250, 80, 12)
      ctx.fill()

      drawText(stats[i].emoji, x + 16, y + 35, { size: 22 })
      drawText(stats[i].value, x + 50, y + 32, { size: 20, weight: 'bold' })
      drawText(stats[i].label, x + 50, y + 55, { color: '#64748b', size: 13 })
    }

    // Mood section
    const moodY = statsY + 220
    if (props.data.topMood) {
      drawText('Most Common Mood', 40, moodY, { color: '#64748b', size: 12, weight: '600' })
      drawText(props.data.topMood.emoji, 40, moodY + 35, { size: 28 })
      drawText(props.data.topMood.label, 80, moodY + 32, { size: 18, weight: '600' })
      drawText(`from ${props.data.moodCount} mood logs`, 80, moodY + 55, { color: '#64748b', size: 13 })
    }

    // Badges
    const badgeY = moodY + 80
    if (props.data.topBadges.length > 0) {
      drawText('Recent Badges', 40, badgeY, { color: '#64748b', size: 12, weight: '600' })
      let badgeX = 40
      for (const badge of props.data.topBadges.slice(0, 6)) {
        drawText(badge.emoji, badgeX, badgeY + 35, { size: 24 })
        badgeX += 45
      }
      if (props.data.badgeCount > 6) {
        drawText(`+${props.data.badgeCount - 6} more`, badgeX + 5, badgeY + 33, { color: '#64748b', size: 13 })
      }
    }

    // Goals completed
    if (props.data.goalsCompleted > 0) {
      drawText(`${props.data.goalsCompleted} goals completed`, 40, badgeY + 75, { color: '#34d399', size: 14, weight: '600' })
    }

    // Footer
    drawText('zugabot.ai', 300, 770, { color: '#475569', size: 13, align: 'center' })

    // Download
    const url = canvas.toDataURL('image/png')
    const a = document.createElement('a')
    a.href = url
    const safeName = (props.data.displayName || 'zugalife').replace(/[^a-zA-Z0-9]/g, '-').toLowerCase()
    a.download = `zugalife-${safeName}-${props.data.date}.png`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } finally {
    capturing.value = false
  }
}

async function shareCard() {
  if (!navigator.share) {
    await downloadCard()
    return
  }

  // Try native Web Share API
  try {
    const card = cardRef.value
    if (!card) return

    // Generate image blob for sharing
    const canvas = document.createElement('canvas')
    canvas.width = 1200
    canvas.height = 1600
    // Same drawing logic would go here, simplified for now:
    await downloadCard() // Fallback to download for now
  } catch {
    await downloadCard()
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      @click.self="emit('close')"
    >
      <div class="glass-card w-full max-w-md mx-4 p-6 animate-slide-up">
        <!-- Header -->
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-txt-primary">Share Your Progress</h3>
          <button @click="emit('close')" class="text-txt-muted hover:text-txt-primary transition-colors">
            <X :size="20" />
          </button>
        </div>

        <!-- Card preview -->
        <div
          ref="cardRef"
          class="rounded-2xl overflow-hidden mb-4"
          style="background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0a0a1a 100%); border-top: 4px solid #6366f1;"
        >
          <div class="p-6">
            <!-- Logo + Date -->
            <div class="flex items-center justify-between mb-4">
              <span class="text-sm font-bold text-accent">ZugaLife</span>
              <span class="text-xs text-txt-muted">{{ formattedDate }}</span>
            </div>

            <!-- Name + Level -->
            <h2 class="text-xl font-bold text-txt-primary">{{ data.displayName || 'My Wellness Journey' }}</h2>
            <p class="text-sm font-semibold text-accent">Level {{ data.level }} — {{ data.levelName }}</p>
            <p v-if="data.prestigeLevel > 0" class="text-xs font-semibold text-amber-400 mt-0.5">Prestige {{ data.prestigeLevel }}</p>

            <!-- XP bar -->
            <div class="mt-3 mb-1">
              <div class="h-2 rounded-full bg-white/5">
                <div class="h-2 rounded-full bg-accent transition-all" style="width: 65%"></div>
              </div>
              <p class="text-[11px] text-txt-muted mt-1 text-right">{{ data.totalXp.toLocaleString() }} XP</p>
            </div>

            <!-- Stats grid -->
            <div class="grid grid-cols-2 gap-2 mt-4">
              <div class="rounded-xl bg-white/5 p-3">
                <div class="flex items-center gap-2">
                  <span class="text-lg">🔥</span>
                  <div>
                    <p class="text-base font-bold text-txt-primary">{{ data.currentStreak }} days</p>
                    <p class="text-[11px] text-txt-muted">Streak</p>
                  </div>
                </div>
              </div>
              <div class="rounded-xl bg-white/5 p-3">
                <div class="flex items-center gap-2">
                  <span class="text-lg">📝</span>
                  <div>
                    <p class="text-base font-bold text-txt-primary">{{ data.journalCount }}</p>
                    <p class="text-[11px] text-txt-muted">Journal entries</p>
                  </div>
                </div>
              </div>
              <div class="rounded-xl bg-white/5 p-3">
                <div class="flex items-center gap-2">
                  <span class="text-lg">🧘</span>
                  <div>
                    <p class="text-base font-bold text-txt-primary">{{ data.meditationMinutes }} min</p>
                    <p class="text-[11px] text-txt-muted">Meditation</p>
                  </div>
                </div>
              </div>
              <div class="rounded-xl bg-white/5 p-3">
                <div class="flex items-center gap-2">
                  <span class="text-lg">✅</span>
                  <div>
                    <p class="text-base font-bold text-txt-primary">{{ Math.round(data.habitCompletionRate * 100) }}%</p>
                    <p class="text-[11px] text-txt-muted">Habit rate</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Mood -->
            <div v-if="data.topMood" class="mt-4">
              <p class="text-[11px] text-txt-muted uppercase tracking-wide mb-1">Most Common Mood</p>
              <div class="flex items-center gap-2">
                <span class="text-2xl">{{ data.topMood.emoji }}</span>
                <div>
                  <span class="text-sm font-semibold text-txt-primary">{{ data.topMood.label }}</span>
                  <span class="text-xs text-txt-muted ml-2">from {{ data.moodCount }} logs</span>
                </div>
              </div>
            </div>

            <!-- Badges -->
            <div v-if="data.topBadges.length > 0" class="mt-4">
              <p class="text-[11px] text-txt-muted uppercase tracking-wide mb-1">Badges</p>
              <div class="flex items-center gap-1">
                <span v-for="b in data.topBadges.slice(0, 6)" :key="b.title" class="text-xl" :title="b.title">{{ b.emoji }}</span>
                <span v-if="data.badgeCount > 6" class="text-xs text-txt-muted ml-1">+{{ data.badgeCount - 6 }} more</span>
              </div>
            </div>

            <!-- Footer -->
            <div class="mt-5 pt-3 border-t border-white/5 text-center">
              <span class="text-xs text-txt-muted">zugabot.ai</span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            @click="downloadCard"
            :disabled="capturing"
            class="flex-1 btn-primary py-2.5 text-sm flex items-center justify-center gap-2"
          >
            <Download :size="16" />
            {{ capturing ? 'Generating...' : 'Download Image' }}
          </button>
          <button
            v-if="navigator.share"
            @click="shareCard"
            class="px-4 py-2.5 text-sm font-medium border border-bdr rounded-xl text-txt-secondary hover:text-accent hover:border-accent/40 transition-all flex items-center gap-2"
          >
            <Share2 :size="16" />
            Share
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
