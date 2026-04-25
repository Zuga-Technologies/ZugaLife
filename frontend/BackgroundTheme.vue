<!--
  Re-export shim — canonical source moved to @core/wallpaper/BackgroundTheme.vue.
  Preserved here so ZugaApp's App.vue import (`@studios/life/frontend/BackgroundTheme.vue`)
  keeps working without changing the consumer.
  New code should import from '@core/wallpaper' instead.
-->
<script setup lang="ts">
import BackgroundTheme from '@core/wallpaper/BackgroundTheme.vue'
defineExpose({ BackgroundTheme })
</script>

<template>
  <BackgroundTheme />
</template>
