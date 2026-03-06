import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@core': resolve(__dirname, '../../ZugaCore/frontend'),
    },
    dedupe: ['vue', 'pinia', 'vue-router'],
  },
  server: {
    port: 5174,
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://192.168.1.200:8000',
        changeOrigin: true,
      },
    },
  },
})
