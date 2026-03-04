import type { Config } from 'tailwindcss'
import preset from '../core/frontend/theme/tailwind.preset'

export default {
  presets: [preset],
  content: [
    './index.html',
    './*.{vue,ts}',
    '../core/frontend/**/*.{ts,css}',
  ],
  plugins: [],
} satisfies Config
