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
    host: true,
    port: 5174,
    allowedHosts: ['.trycloudflare.com'],
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
