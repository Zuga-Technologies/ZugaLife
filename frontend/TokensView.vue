<script setup lang="ts">
import { useRouter } from 'vue-router'
import { BillingPanel } from '@core/billing'
import { ArrowLeft } from 'lucide-vue-next'

const router = useRouter()
</script>

<template>
  <div class="min-h-screen bg-surface-0 text-txt-primary">
    <div class="max-w-lg mx-auto px-4 py-8">
      <!-- Back button -->
      <button
        @click="router.push('/')"
        class="flex items-center gap-2 text-sm text-txt-muted hover:text-txt-primary transition-colors mb-6"
      >
        <ArrowLeft :size="16" />
        Back to Life
      </button>

      <h1 class="text-2xl font-bold mb-6">ZugaTokens</h1>

      <BillingPanel />
    </div>
  </div>
</template>
